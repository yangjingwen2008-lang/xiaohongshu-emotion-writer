import os
import shutil
from pathlib import Path

import pytest


TEST_DATA = Path(__file__).parent / ".test_data"
if TEST_DATA.exists():
    shutil.rmtree(TEST_DATA)
os.environ["XR_DATA_DIR"] = str(TEST_DATA)
os.environ["XR_LOG_DIR"] = str(TEST_DATA / "logs")
os.environ["XR_EXPORT_DIR"] = str(TEST_DATA / "exports")
os.environ["XR_UPLOAD_DIR"] = str(TEST_DATA / "uploads")
os.environ["XR_TEST_MODE"] = "true"


@pytest.fixture(autouse=True)
def clean_fts_index():
    from backend.app.database import engine

    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS content_search_fts")
    yield
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS content_search_fts")
