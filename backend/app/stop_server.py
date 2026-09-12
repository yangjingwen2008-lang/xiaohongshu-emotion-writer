import os
import subprocess
import signal
import sys
import json
import re

from .config import settings


def owns_windows_process(pid: int) -> bool:
    """Fail closed if a stale PID now belongs to another app or checkout."""
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-Command',
         '$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); '
         f'Get-CimInstance Win32_Process -Filter "ProcessId = {int(pid)}" | Select-Object CommandLine | ConvertTo-Json -Compress'],
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        raise RuntimeError('无法核对服务进程身份，未停止任何程序。')
    if not result.stdout.strip():
        raise ProcessLookupError(pid)
    process = json.loads(result.stdout)
    command = (process.get('CommandLine') or '').replace('\\', '/').lower()
    executable = sys.executable.replace('\\', '/').lower()
    return executable in command and bool(re.search(r'-m\s+backend\.app\.run_server(?:\s|$)', command))


def main() -> None:
    pid_file = settings.data_dir / "server.pid"
    if not pid_file.exists():
        print("服务未运行。")
        return
    try:
        pid = int(pid_file.read_text(encoding="ascii").strip())
        if pid <= 0:
            raise ValueError('invalid PID')
        if sys.platform == "win32":
            if not owns_windows_process(pid):
                print('PID 已被其他进程使用，未停止该进程；已清除本项目过期记录。')
                pid_file.unlink(missing_ok=True)
                return
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                summary = (result.stderr or result.stdout or "未知错误").strip()[:500]
                print(f"停止失败，PID 记录已保留：{summary}")
                raise SystemExit(1)
        else:
            os.kill(pid, signal.SIGTERM)
        pid_file.unlink(missing_ok=True)
        print(f"已停止潮湿雨季，PID={pid}")
    except (ValueError, ProcessLookupError):
        print("PID 记录已过期，服务当前未运行。")
        pid_file.unlink(missing_ok=True)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f'停止失败，启动记录已保留：{exc}')
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
