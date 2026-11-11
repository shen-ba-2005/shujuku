# One-file Windows launcher. MySQL is shipped beside the executable.
from pathlib import Path

root = Path(SPECPATH)
a = Analysis(
    [str(root / "launch_entry.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "frontend"), "frontend"),
        (str(root / "database"), "database"),
    ],
    hiddenimports=["backend.app", "scripts.dev", "pymysql", "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="屿账",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)
