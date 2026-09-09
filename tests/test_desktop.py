"""Unit tests for double_chin.desktop.

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

import re
from pathlib import Path

import double_chin
from double_chin.desktop import (
    _LAUNCH_COLOR_DARK,
    _LAUNCH_COLOR_LIGHT,
    _acquire_single_instance_lock,
    _is_multiprocessing_child,
    _launch_background_color,
)


def test_genuine_launch_argv_is_not_a_multiprocessing_child():
    assert _is_multiprocessing_child(["Double Chin"]) is False


def test_spawned_worker_argv_is_a_multiprocessing_child():
    argv = ["Double Chin", "--multiprocessing-fork", "tracker_fd=3", "pipe_handle=4"]
    assert _is_multiprocessing_child(argv) is True


def test_resource_tracker_bootstrap_argv_is_a_multiprocessing_child():
    argv = [
        "Double Chin",
        "-c",
        "from multiprocessing.resource_tracker import main;main(3)",
    ]
    assert _is_multiprocessing_child(argv) is True


def test_short_argv_is_not_a_multiprocessing_child():
    # Guards against an index error on argv shorter than the '-c' check expects.
    assert _is_multiprocessing_child(["Double Chin"]) is False
    assert _is_multiprocessing_child([]) is False


def test_single_instance_lock_blocks_second_acquire(tmp_path, monkeypatch):
    monkeypatch.setenv("DOUBLECHIN_HOME", str(tmp_path / "home"))

    first = _acquire_single_instance_lock()
    try:
        assert first is not None
        second = _acquire_single_instance_lock()
        assert second is None
    finally:
        if hasattr(first, "close"):
            first.close()


def test_single_instance_lock_releases_after_close(tmp_path, monkeypatch):
    monkeypatch.setenv("DOUBLECHIN_HOME", str(tmp_path / "home"))

    first = _acquire_single_instance_lock()
    assert first is not None
    if hasattr(first, "close"):
        first.close()

    second = _acquire_single_instance_lock()
    assert second is not None
    if hasattr(second, "close"):
        second.close()


class TestLaunchBackgroundColor:
    """The window's pre-paint fill must track the interface's own canvas.

    These are two files that have to agree: `desktop.py` picks the colour the
    native window shows before the page loads, and `tokens.css` defines the
    colour the page then paints. When they drift, every launch flashes.
    """

    def test_dark_appearance_uses_the_dark_launch_colour(self):
        assert _launch_background_color(prefers_dark=lambda: True) == _LAUNCH_COLOR_DARK

    def test_light_appearance_uses_the_light_launch_colour(self):
        assert _launch_background_color(prefers_dark=lambda: False) == _LAUNCH_COLOR_LIGHT

    def test_launch_colours_match_the_canvas_tokens_in_css(self):
        tokens = (
            Path(double_chin.__file__).parent / "studio" / "static" / "tokens.css"
        ).read_text()
        canvases = re.findall(r"--bg-grouped:\s*(#[0-9A-Fa-f]{6});", tokens)

        assert canvases == [_LAUNCH_COLOR_LIGHT, _LAUNCH_COLOR_DARK], (
            "tokens.css --bg-grouped values drifted from desktop.py's launch colours; "
            f"css has {canvases}"
        )
