"""Unit tests for double_chin.config."""

from __future__ import annotations

from pathlib import Path

from double_chin import config


def test_double_chin_home_defaults_to_dot_double_chin(monkeypatch):
    monkeypatch.delenv("DOUBLECHIN_HOME", raising=False)
    assert config.double_chin_home() == Path.home() / ".double-chin"


def test_double_chin_home_honours_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("DOUBLECHIN_HOME", str(tmp_path / "custom"))
    assert config.double_chin_home() == tmp_path / "custom"


def test_voices_dir_is_under_double_chin_home(tmp_path, monkeypatch):
    monkeypatch.setenv("DOUBLECHIN_HOME", str(tmp_path / "custom"))
    assert config.voices_dir() == tmp_path / "custom" / "voices"


def test_ensure_dir_creates_missing_directory(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    result = config.ensure_dir(target)
    assert result == target
    assert target.is_dir()
