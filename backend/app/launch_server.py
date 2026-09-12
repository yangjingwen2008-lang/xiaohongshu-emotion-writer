"""Idempotent Windows launcher shared by the desktop batch entry points."""
import argparse
import socket
import subprocess
import sys
import webbrowser

from .config import ROOT_DIR, settings
from .server_status import is_server_ready, wait_until_ready
from .stop_server import main as stop_server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--lan', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not (ROOT_DIR / 'frontend/dist/index.html').is_file():
        raise SystemExit('前端尚未构建，请先运行安装脚本。')
    settings.ensure_directories()
    if not is_server_ready():
        if (settings.data_dir / 'server.pid').exists():
            stop_server()
        command = [sys.executable, '-m', 'backend.app.run_server']
        if args.lan:
            command.append('--lan')
        with (settings.log_dir / 'startup.log').open('ab') as log:
            subprocess.Popen(command, cwd=ROOT_DIR, stdout=log, stderr=log,
                             stdin=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        if not wait_until_ready(45):
            raise SystemExit(f'服务未就绪，请查看 {settings.log_dir / "startup.log"}；端口冲突时不会停止其他程序。')
    elif args.lan:
        print('现有服务已复用。如需从本机切换为局域网模式，请先运行停止脚本。')
    url = f'http://127.0.0.1:{settings.port}'
    print(f'工作台已就绪：{url}')
    if args.lan:
        try:
            print(f'局域网地址（仅局域网模式可访问）：http://{socket.gethostbyname(socket.gethostname())}:{settings.port}')
        except OSError:
            print('未能确定局域网地址。')
    if not args.no_browser:
        webbrowser.open(url)


if __name__ == '__main__':
    main()
