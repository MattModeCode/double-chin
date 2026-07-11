"""Unit tests for myna.config."""

from __future__ import annotations

from pathlib import Path

from myna import config


def test_myna_home_defaults_to_dot_myna(monkeypatch):
    monkeypatch.delenv("MYNA_HOME", raising=False)
    assert config.myna_home() == Path.home() / ".myna"


def test_myna_home_honours_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("MYNA_HOME", str(tmp_path / "custom"))
    assert config.myna_home() == tmp_path / "custom"


def test_voices_dir_is_under_myna_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MYNA_HOME", str(tmp_path / "custom"))
    assert config.voices_dir() == tmp_path / "custom" / "voices"


def test_ensure_dir_creates_missing_directory(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    result = config.ensure_dir(target)
    assert result == target
    assert target.is_dir()
