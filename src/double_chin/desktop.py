"""Native desktop shell for Double Chin.

Opens the same local server used by `double-chin studio` in a real desktop
window (the system WebView via pywebview) instead of a browser tab — its
own window, its own title bar, no browser chrome. No server-side changes
are needed: `create_app()` already accepts any request whose Host/Origin
resolve to loopback (see `studio/app.py`'s same-origin guard), and a
WebView pointed at 127.0.0.1 satisfies that.
"""

from __future__ import annotations

import socket
import sys
import threading
import time

import uvicorn

_PREFERRED_PORT = 8787
_STARTUP_TIMEOUT_SECONDS = 15.0
_STARTUP_POLL_SECONDS = 0.05


def _pick_port() -> int:
    """Prefer the well-known Studio port; fall back to any free loopback port."""
    for port in (_PREFERRED_PORT, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return probe.getsockname()[1]
    raise RuntimeError("no free loopback port available")


def _wait_until_accepting(port: int, timeout: float = _STARTUP_TIMEOUT_SECONDS) -> None:
    """Block until something is accepting connections on `port`, or raise."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(_STARTUP_POLL_SECONDS)
    raise RuntimeError(f"server on port {port} did not start within {timeout:.0f}s")


def _is_multiprocessing_child(argv: list[str]) -> bool:
    """True if `argv` is a re-exec of this entry point as a multiprocessing helper.

    In a PyInstaller-frozen app, every multiprocessing child re-executes the
    same entry point (there is no separate `python` interpreter to fork from)
    — so this file's `__main__` block runs again for each one. Two shapes
    need to be caught and dispatched instead of falling through to `run()`:
    spawned workers (`multiprocessing.spawn.is_forking`, e.g.
    `argv[1] == '--multiprocessing-fork'`) and the resource/semaphore
    tracker, which bootstraps via `<exe> -c '<code>' <fd>`.
    """
    import multiprocessing.spawn as spawn

    return spawn.is_forking(argv) or (len(argv) >= 2 and argv[-2] == "-c")


def _acquire_single_instance_lock() -> object | None:
    """Try to become the sole Double Chin instance; return a handle to keep alive.

    Returns an opaque object that must stay referenced for the process
    lifetime (its finalization/GC is irrelevant — the OS releases the lock
    on process exit regardless). Returns None if another instance already
    holds the lock. On platforms without `fcntl` (non-Unix), the guard is
    skipped entirely and a no-op sentinel is returned so callers never treat
    "can't lock" as "already running".
    """
    try:
        import fcntl
    except ImportError:
        return object()

    from double_chin.config import double_chin_home, ensure_dir

    lock_path = ensure_dir(double_chin_home()) / "app.lock"
    handle = open(lock_path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def run() -> int:
    """Launch Double Chin as a native desktop window. Blocks until the window closes."""
    import webview  # deferred: pulls in pyobjc on macOS, only needed for this path

    from double_chin.config import migrate_legacy_home
    from double_chin.studio.app import create_app

    migrate_legacy_home()

    lock = _acquire_single_instance_lock()
    if lock is None:
        # Another Double Chin window already owns this session — exit quietly
        # rather than opening a second, independent server/window.
        return 0

    port = _pick_port()
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    _wait_until_accepting(port)

    window = webview.create_window(
        "Double Chin",
        f"http://127.0.0.1:{port}",
        width=1160,
        height=780,
        min_size=(760, 560),
    )
    window.events.closed += lambda: setattr(server, "should_exit", True)

    webview.start()

    server.should_exit = True
    server_thread.join(timeout=5.0)
    return 0


if __name__ == "__main__":
    # Entry point for the bundled Double Chin.app (see packaging/double-chin.spec):
    # double-clicking the app runs this file directly, no CLI parsing needed.
    #
    # Torch's inference path spawns multiprocessing helpers (start method
    # "spawn" on macOS: worker processes, plus a resource/semaphore tracker
    # process created lazily on first use). In a PyInstaller-frozen
    # executable there is no separate `python` interpreter to fork from, so
    # each helper re-executes this same entry point from scratch.
    #
    # multiprocessing.freeze_support() (the top-level one) does NOT catch
    # this here — per the stdlib, it is a no-op unless
    # `sys.platform == "win32"`. Left unguarded on macOS/Linux, a re-executed
    # helper falls straight through to run() again — a second server plus a
    # second webview window opening right after the first "Generate".
    #
    # Dispatch explicitly instead: run the real helper code and exit before
    # ever reaching run(). Only a genuine app launch (argv carrying neither
    # shape) reaches run().
    import multiprocessing.spawn as _spawn

    if _is_multiprocessing_child(sys.argv):
        if _spawn.is_forking(sys.argv):
            _spawn.freeze_support()  # runs the spawned worker; calls sys.exit() itself
        else:
            exec(sys.argv[-1])  # resource/semaphore tracker bootstrap: main(fd)
            raise SystemExit(0)
    else:
        raise SystemExit(run())
