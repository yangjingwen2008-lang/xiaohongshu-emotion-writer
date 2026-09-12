import argparse
import asyncio
import logging

from .database import SessionLocal
from .logging_config import configure_logging
from .trends import TrendError, TrendService


async def run(trigger: str) -> int:
    with SessionLocal() as db:
        try:
            result = await TrendService(db).refresh(trigger=trigger)
        except TrendError as exc:
            logging.getLogger(__name__).error("热点刷新失败 run_id=%s error=%s", exc.run_id, exc)
            return 1
        logging.getLogger(__name__).info(
            "热点刷新完成 run_id=%s trigger=%s sources=%s candidates=%s status=%s",
            result.id,
            trigger,
            result.source_count,
            result.candidate_count,
            result.data_status,
        )
        return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trigger", choices=["manual", "scheduled"], default="scheduled")
    args = parser.parse_args()
    configure_logging()
    raise SystemExit(asyncio.run(run(args.trigger)))


if __name__ == "__main__":
    main()
