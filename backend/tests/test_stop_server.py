import subprocess

import pytest

from backend.app.config import settings
from backend.app import stop_server


def test_stop_server_keeps_pid_record_when_taskkill_fails(monkeypatch: pytest.MonkeyPatch):
    pid_file = settings.data_dir / "server.pid"
    pid_file.write_text("12345", encoding="ascii")
    monkeypatch.setattr(stop_server.sys, "platform", "win32")
    monkeypatch.setattr(stop_server, 'owns_windows_process', lambda _pid: True)
    monkeypatch.setattr(
        stop_server.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "访问被拒绝"),
    )

    with pytest.raises(SystemExit) as error:
        stop_server.main()

    assert error.value.code == 1
    assert pid_file.read_text(encoding="ascii") == "12345"
    pid_file.unlink()


def test_stop_server_removes_pid_record_only_after_success(monkeypatch: pytest.MonkeyPatch):
    pid_file = settings.data_dir / "server.pid"
    pid_file.write_text("12345", encoding="ascii")
    monkeypatch.setattr(stop_server.sys, "platform", "win32")
    monkeypatch.setattr(stop_server, 'owns_windows_process', lambda _pid: True)
    monkeypatch.setattr(
        stop_server.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "成功", ""),
    )

    stop_server.main()

    assert not pid_file.exists()


def test_stale_pid_does_not_stop_an_unrelated_process(monkeypatch):
    pid_file = settings.data_dir / 'server.pid'
    pid_file.write_text('12345', encoding='ascii')
    monkeypatch.setattr(stop_server.sys, 'platform', 'win32')
    monkeypatch.setattr(stop_server, 'owns_windows_process', lambda _pid: False)
    def unexpected_kill(*_args, **_kwargs):
        pytest.fail('must not kill an unrelated process')
    monkeypatch.setattr(stop_server.subprocess, 'run', unexpected_kill)
    stop_server.main()
    assert not pid_file.exists()
