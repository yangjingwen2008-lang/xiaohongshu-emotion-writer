"""Create a source-only release folder and ZIP without touching personal runtime data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    '.env.example', '.gitignore', '.dockerignore', '.gitattributes', '.editorconfig',
    'README.md', 'CHANGELOG.md', 'CONTRIBUTING.md', 'SECURITY.md',
    'pyproject.toml', 'requirements.lock.txt', 'alembic.ini', 'Dockerfile', 'compose.yaml',
    '安装潮湿雨季.bat', '启动潮湿雨季.bat', '启动潮湿雨季_局域网.bat', '停止潮湿雨季.bat',
}
SOURCE_TREES = {'backend', 'frontend', 'scripts', 'docs', '.github'}
EXCLUDED = {'.git', '.venv', '__pycache__', '.pytest_cache', '.test_data', 'node_modules',
            'dist', 'coverage', '.agents', '.codex', '.work', 'release'}
EXTENSIONS = {'.py', '.ps1', '.bat', '.json', '.toml', '.yaml', '.yml', '.ini', '.mako',
              '.md', '.tsx', '.ts', '.css', '.html', '.svg', '.png', '.jpg', '.webp'}
TOKEN_PATTERN = re.compile(r'\b(?:sk-|tvly-)[A-Za-z0-9_-]{24,}\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
PERSONAL_PATH = re.compile(r'(?:[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s`"\']+|' + '/' + 'Users' + r'/[^/\s]+)')


def source_files(root: Path):
    for directory, subdirectories, names in os.walk(root, followlinks=False):
        parent = Path(directory)
        subdirectories[:] = sorted(name for name in subdirectories
                                   if name not in EXCLUDED and not name.endswith('.egg-info')
                                   and not (parent / name).is_symlink()
                                   and (parent != root or name in SOURCE_TREES))
        for name in sorted(names):
            path = parent / name
            if path.is_symlink():
                continue
            if parent == root:
                if name in ROOT_FILES:
                    yield path
            elif name.startswith('.env') or path.suffix in {'.db', '.pem', '.key'}:
                continue
            elif path.suffix in EXTENSIONS or name == '.gitignore':
                yield path


def prepare(root: Path, destination: Path) -> tuple[Path, int]:
    root, destination = root.resolve(), destination.resolve()
    if destination == root or destination in root.parents:
        raise ValueError('发布目录不能覆盖源项目或其父目录。')
    archive = destination.with_name(destination.name + '.zip')
    if destination.exists() or archive.exists():
        raise FileExistsError('目标目录或 ZIP 已存在，请选择一个新目录；不会覆盖已有文件。')
    files = list(source_files(root))
    records = []
    snapshots = []
    for path in files:
        raw = path.read_bytes()
        if path.suffix not in {'.png', '.jpg', '.webp'}:
            content = raw.decode('utf-8-sig')
            if TOKEN_PATTERN.search(content) or PERSONAL_PATH.search(content):
                raise ValueError(f'发现疑似密钥或个人绝对路径，请人工检查：{path.relative_to(root)}')
        records.append({'path': path.relative_to(root).as_posix(), 'bytes': len(raw),
                        'sha256': hashlib.sha256(raw).hexdigest()})
        snapshots.append((path.relative_to(root), raw))
    destination.mkdir(parents=True)
    for relative_path, raw in snapshots:
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    (destination / 'RELEASE_MANIFEST.json').write_text(json.dumps({
        'format': 1, 'includes_git_history': False, 'files': records,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(destination.rglob('*')):
            if path.is_file():
                zipped.write(path, Path(destination.name) / path.relative_to(destination))
    return archive, len(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'release/chaoshi-yuji')
    args = parser.parse_args()
    archive, count = prepare(ROOT, args.output)
    print(f'已整理 {count} 个源码与文档文件：{args.output.resolve()}')
    print(f'压缩包：{archive}')
    print('未连接或上传 GitHub。')


if __name__ == '__main__':
    main()
