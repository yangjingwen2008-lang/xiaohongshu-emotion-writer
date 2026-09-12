import subprocess
import sys
from pathlib import Path

from .config import ROOT_DIR


TASKS = {
    "09:00": "潮湿雨季-热点刷新-0900",
    "20:00": "潮湿雨季-热点刷新-2000",
}


class TrendSchedulerError(RuntimeError):
    pass


def _supported() -> bool:
    return sys.platform == "win32"


def _task_command() -> str:
    script = (ROOT_DIR / "scripts" / "run_trend_refresh.bat").resolve()
    return f'"{script}"'


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if _supported() else 0,
    )


def schedule_status() -> dict:
    if not _supported():
        return {"supported": False, "installed": False, "times": list(TASKS), "tasks": []}
    tasks = []
    for time_value, name in TASKS.items():
        result = _run(["schtasks.exe", "/Query", "/TN", name])
        tasks.append({"name": name, "time": time_value, "installed": result.returncode == 0})
    return {
        "supported": True,
        "installed": all(item["installed"] for item in tasks),
        "times": list(TASKS),
        "tasks": tasks,
        "missed_run_policy": "电脑关机或错过时不补跑，等待下一次计划时间。",
    }


def uninstall_schedule() -> dict:
    if not _supported():
        raise TrendSchedulerError("Windows 任务计划程序仅在 Windows 本机可用")
    for name in TASKS.values():
        _run(["schtasks.exe", "/Delete", "/F", "/TN", name])
    return schedule_status()


def install_schedule() -> dict:
    if not _supported():
        raise TrendSchedulerError("Windows 任务计划程序仅在 Windows 本机可用")
    created: list[str] = []
    for time_value, name in TASKS.items():
        result = _run(
            [
                "schtasks.exe",
                "/Create",
                "/F",
                "/SC",
                "DAILY",
                "/ST",
                time_value,
                "/TN",
                name,
                "/TR",
                _task_command(),
                "/RL",
                "LIMITED",
            ]
        )
        if result.returncode != 0:
            for created_name in created:
                _run(["schtasks.exe", "/Delete", "/F", "/TN", created_name])
            summary = (result.stderr or result.stdout or "未知错误").strip()[:500]
            raise TrendSchedulerError(f"创建 {time_value} 热点计划任务失败：{summary}")
        created.append(name)
    return schedule_status()
