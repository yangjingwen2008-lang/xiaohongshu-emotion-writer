import os
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_migrations_use_configured_data_directory_and_are_repeatable(tmp_path):
    data = tmp_path / 'isolated data'
    env = dict(os.environ, XR_DATA_DIR=str(data), XR_LOG_DIR=str(tmp_path / 'logs'),
               XR_UPLOAD_DIR=str(tmp_path / 'uploads'), XR_EXPORT_DIR=str(tmp_path / 'exports'))
    for _ in range(2):
        result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT,
                                env=env, capture_output=True, text=True, errors='replace')
        assert result.returncode == 0, result.stderr
    with closing(sqlite3.connect(data / 'chaoshi_yuji.db')) as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()
        assert db.execute("SELECT name FROM sqlite_master WHERE name='contents'").fetchone()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows PowerShell installer')
def test_installer_stops_before_build_and_migration_after_pip_failure(tmp_path):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    shutil.copy2(ROOT / 'scripts/bootstrap.ps1', scripts / 'bootstrap.ps1')
    # A .cmd named python simulates the interpreter, then creates a native executable
    # that reliably fails pip: Windows where.exe receives unsupported pip arguments.
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    (tmp_path / '.venv/Scripts').mkdir(parents=True)
    shutil.copy2(Path(os.environ['SystemRoot']) / 'System32/where.exe', tmp_path / '.venv/Scripts/python.exe')
    (fake_bin / 'python.cmd').write_text('@echo off\nexit /b 0\n')
    (fake_bin / 'node.cmd').write_text('@echo off\nexit /b 0\n')
    (fake_bin / 'npm.cmd').write_text('@echo off\necho unexpected>npm-was-called.txt\nexit /b 0\n')
    env = dict(os.environ, PATH=str(fake_bin) + os.pathsep + os.environ['PATH'])
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                             '-File', str(scripts / 'bootstrap.ps1')], cwd=tmp_path, env=env,
                            capture_output=True)
    assert result.returncode == 1
    assert not (tmp_path / 'npm-was-called.txt').exists()
    assert not (tmp_path / 'data').exists()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows PowerShell installer')
def test_installer_check_only_does_not_create_environment(tmp_path):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    shutil.copy2(ROOT / 'scripts/bootstrap.ps1', scripts / 'bootstrap.ps1')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                             '-File', str(scripts / 'bootstrap.ps1'), '-CheckOnly'], cwd=tmp_path,
                            capture_output=True)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / '.venv').exists()
    assert not (tmp_path / 'data').exists()
