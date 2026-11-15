# PyInstaller spec: `onedir` build of the real app (entry: the Launcher).
#
# Run from the repository root, after building Angular (output: backend/app/static):
#   cd backend && uv run --group build pyinstaller --noconfirm \
#       --distpath ../packaging/dist --workpath ../packaging/build ../packaging/youtube-downloader.spec
#
# macOS: arm64 onedir (the .app bundle, icon and ad-hoc signing belong to ticket 12).
# Windows: no console window (icon and zip belong to ticket 13).
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - SPECPATH is injected by PyInstaller
BACKEND = ROOT / "backend"
STATIC = BACKEND / "app" / "static"

if not (STATIC / "index.html").is_file():
    raise SystemExit(f"Angular build not found in {STATIC}: run `npm run build` in frontend/ first.")

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(BACKEND)],
    # `datas` pairs use the platform-independent (source, dest) tuple form: no `:`/`;` separator.
    datas=[(str(STATIC), "static")],
    # uvicorn picks its loop/protocol implementations by name at runtime.
    hiddenimports=collect_submodules("uvicorn"),
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="youtube-downloader",
    console=sys.platform != "win32",
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    name="youtube-downloader",
)
