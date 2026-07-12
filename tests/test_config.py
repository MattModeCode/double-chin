"""Unit tests for chinai.config."""

from __future__ import annotations

from pathlib import Path

from chinai import config


def test_chinai_home_defaults_to_dot_chinai(monkeypatch):
    monkeypatch.delenv("CHINAI_HOME", raising=False)
    assert config.chinai_home() == Path.home() / ".chinai"


def test_chinai_home_honours_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CHINAI_HOME", str(tmp_path / "custom"))
    assert config.chinai_home() == tmp_path / "custom"


def test_voices_dir_is_under_chinai_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CHINAI_HOME", str(tmp_path / "custom"))
    assert config.voices_dir() == tmp_path / "custom" / "voices"


def test_ensure_dir_creates_missing_directory(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    result = config.ensure_dir(target)
    assert result == target
    assert target.is_dir()
