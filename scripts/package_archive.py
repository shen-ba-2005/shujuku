"""Archive the verified release, including runtime/licenses, never user data."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'release' / '屿账'
ARCHIVE = ROOT / 'release' / 'shujuku-windows-x64.zip'


def main():
    required = ['屿账.exe', '使用说明.txt', 'mysql/bin/mysqld.exe', 'mysql/LICENSE']
    for entry in required:
        if not (SOURCE / entry).is_file():
            raise SystemExit('发布文件缺失：' + entry)
    files = [SOURCE / '屿账.exe', SOURCE / '使用说明.txt']
    files.extend(sorted(p for p in (SOURCE / 'mysql').rglob('*') if p.is_file()))
    for file in files:
        # A release never includes user database files, keys, or local config.
        if file.is_symlink() or file.suffix.lower() in {'.pem', '.key', '.ibd', '.log'}:
            raise SystemExit('发布目录包含不应分发的文件：' + str(file.relative_to(SOURCE)))
        if file.name.lower() in {'db.json', 'my.ini', 'auto.cnf', 'mysqld-auto.cnf'}:
            raise SystemExit('发布目录包含本机数据或配置：' + str(file.relative_to(SOURCE)))
    with zipfile.ZipFile(ARCHIVE, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file in files:
            archive.write(file, Path('屿账') / file.relative_to(SOURCE))
    with zipfile.ZipFile(ARCHIVE) as archive:
        bad = archive.testzip()
        if bad:
            raise SystemExit('压缩包完整性检查失败：' + bad)
        assert len(archive.namelist()) == len(files)
    with ARCHIVE.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    ARCHIVE.with_suffix('.zip.sha256').write_text(
        f'{digest}  {ARCHIVE.name}\n', encoding='ascii', newline='\n')
    manifest = {
        'version': 'v0.8.1', 'archive': ARCHIVE.name, 'bytes': ARCHIVE.stat().st_size,
        'sha256': digest, 'files': len(files),
        'launcher_sha256': hashlib.sha256((SOURCE / '屿账.exe').read_bytes()).hexdigest(),
        'includes': ['Windows x64 launcher', 'MySQL server and original licenses', '使用说明.txt'],
        'excludes': ['user database', 'credentials', 'development environment'],
    }
    (ROOT / 'docs/evidence/windows-release.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
