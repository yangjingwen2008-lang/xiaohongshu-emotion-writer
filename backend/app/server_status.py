import argparse
import json
import time
from urllib.request import urlopen
from .config import instance_id, settings


HEALTH_URL = f"http://127.0.0.1:{settings.port}/api/health"


def is_server_ready(request_timeout: float = 1.0) -> bool:
    try:
        with urlopen(HEALTH_URL, timeout=request_timeout) as response:  # noqa: S310 - fixed localhost URL
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("status") == "ok" and payload.get("instance_id") == instance_id()
    except (OSError, ValueError):
        return False


def wait_until_ready(wait_seconds: float = 45.0, interval: float = 0.5) -> bool:
    deadline = time.monotonic() + max(0.0, wait_seconds)
    while True:
        if is_server_ready():
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(interval, remaining))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait", type=float, default=0.0)
    args = parser.parse_args()
    if wait_until_ready(args.wait):
        print(f"服务已就绪：http://127.0.0.1:{settings.port}")
        return
    print("服务未能在规定时间内就绪。")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
