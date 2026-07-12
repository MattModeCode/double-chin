"""Unit tests for chinai.cli."""

from __future__ import annotations

import pytest

from chinai.cli import main


def test_help_exits_zero():
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


def test_unknown_command_exits_two():
    with pytest.raises(SystemExit) as exc_info:
        main(["bogus-command"])
    assert exc_info.value.code == 2


def test_no_command_exits_two():
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code == 2


def test_voices_on_empty_home_prints_hint(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHINAI_HOME", str(tmp_path / "home"))
    exit_code = main(["voices"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "No voices enrolled" in captured.out


def test_doctor_runs_offline_and_exits_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CHINAI_HOME", str(tmp_path / "home"))
    exit_code = main(["doctor"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "python:" in captured.out
    assert "chinai home:" in captured.out


def test_verify_missing_file_exits_two(tmp_path, capsys):
    missing = tmp_path / "missing.wav"
    exit_code = main(["verify", str(missing), str(missing)])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "chinai: error:" in captured.err
