import argparse
import os
import socket

import uvicorn

from .config import settings
from .server_status import is_server_ready


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lan", action="store_true")
    args = parser.parse_args()
    settings.ensure_directories()
    if is_server_ready():
        print("当前项目的服务已在运行。")
        return
    host = "0.0.0.0" if args.lan else settings.host
    with socket.socket() as probe:
        try:
            probe.bind((host, settings.port))
        except OSError as exc:
            raise SystemExit(f"端口 {settings.port} 已被占用，未启动新实例。") from exc
    pid_file = settings.data_dir / "server.pid"
    try:
        with pid_file.open("x", encoding="ascii") as pid_handle:
            pid_handle.write(str(os.getpid()))
    except FileExistsError as exc:
        raise SystemExit("已存在启动记录，请先运行停止脚本，再重新启动。") from exc
    try:
        uvicorn.run("backend.app.main:app", host=host, port=settings.port)
    finally:
        if pid_file.exists() and pid_file.read_text(encoding="ascii").strip() == str(os.getpid()):
            pid_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
