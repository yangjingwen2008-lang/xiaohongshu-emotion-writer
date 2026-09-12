import importlib.util
import hashlib
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('prepare_release', Path(__file__).resolve().parents[2] / 'scripts/prepare_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_release_excludes_personal_data_and_preserves_source(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    for name in ['README.md', 'backend/app/main.py', 'backend/tests/.test_data/private.json',
                 'frontend/node_modules/package/index.ts', 'data/private.json', '.env', '.git/config']:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('example', encoding='utf-8')
    destination = tmp_path / 'public-v0.1.0'
    archive, count = release.prepare(root, destination)
    assert archive == tmp_path / 'public-v0.1.0.zip'
    assert count == 2
    assert (destination / 'backend/app/main.py').exists()
    assert not (destination / 'data').exists()
    assert not (destination / '.env').exists()
    assert not (destination / '.git').exists()
    assert archive.exists()
    assert (root / '.env').read_text() == 'example'
    with pytest.raises(FileExistsError):
        release.prepare(root, destination)


def test_release_stops_before_copying_a_suspected_secret(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    (root / 'README.md').write_text('sk-' + 'a' * 32)
    destination = tmp_path / 'public'
    with pytest.raises(ValueError, match='README'):
        release.prepare(root, destination)
    assert not destination.exists()


def test_release_copies_the_exact_bytes_that_were_scanned(tmp_path, monkeypatch):
    root = tmp_path / 'source'
    root.mkdir()
    source = root / 'README.md'
    source.write_bytes(b'checked source')
    destination = tmp_path / 'public'
    original_mkdir = Path.mkdir

    def mutate_after_scan(path, *args, **kwargs):
        if path == destination:
            source.write_bytes(b'changed after scan')
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'mkdir', mutate_after_scan)
    release.prepare(root, destination)
    assert (destination / 'README.md').read_bytes() == b'checked source'
    manifest = json.loads((destination / 'RELEASE_MANIFEST.json').read_text())
    assert manifest['files'][0]['sha256'] == hashlib.sha256(b'checked source').hexdigest()
