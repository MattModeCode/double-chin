"""Unit tests for chinai.desktop.

Covers the two bugs fixed in the desktop shell:
1. A PyInstaller-frozen build re-executes this entry point for every
   multiprocessing helper (spawned worker, resource/semaphore tracker).
   `_is_multiprocessing_child` must recognize both shapes so `__main__`
   dispatches them instead of falling through to `run()` and opening a
   second server/window.
2. `_acquire_single_instance_lock` must let exactly one process hold the
   lock at a time, so a genuine second launch doesn't open a duplicate
   window either.
"""

from __future__ import annotations

from chinai.desktop import _acquire_single_instance_lock, _is_multiprocessing_child


def test_genuine_launch_argv_is_not_a_multiprocessing_child():
    assert _is_multiprocessing_child(["ChinAI"]) is False


def test_spawned_worker_argv_is_a_multiprocessing_child():
    argv = ["ChinAI", "--multiprocessing-fork", "tracker_fd=3", "pipe_handle=4"]
    assert _is_multiprocessing_child(argv) is True


def test_resource_tracker_bootstrap_argv_is_a_multiprocessing_child():
    argv = [
        "ChinAI",
        "-c",
        "from multiprocessing.resource_tracker import main;main(3)",
    ]
    assert _is_multiprocessing_child(argv) is True


def test_short_argv_is_not_a_multiprocessing_child():
    # Guards against an index error on argv shorter than the '-c' check expects.
    assert _is_multiprocessing_child(["ChinAI"]) is False
    assert _is_multiprocessing_child([]) is False


def test_single_instance_lock_blocks_second_acquire(tmp_path, monkeypatch):
    monkeypatch.setenv("CHINAI_HOME", str(tmp_path / "home"))

    first = _acquire_single_instance_lock()
    try:
        assert first is not None
        second = _acquire_single_instance_lock()
        assert second is None
    finally:
        if hasattr(first, "close"):
            first.close()


def test_single_instance_lock_releases_after_close(tmp_path, monkeypatch):
    monkeypatch.setenv("CHINAI_HOME", str(tmp_path / "home"))

    first = _acquire_single_instance_lock()
    assert first is not None
    if hasattr(first, "close"):
        first.close()

    second = _acquire_single_instance_lock()
    assert second is not None
    if hasattr(second, "close"):
        second.close()
