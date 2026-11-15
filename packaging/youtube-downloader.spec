# PyInstaller spec: `onedir` build of the real app (entry: the Launcher).
#
# Run from the repository root, after building Angular (output: backend/app/static):
#   cd backend && uv run --group build pyinstaller --noconfirm \
#       --distpath ../packaging/dist --workpath ../packaging/build ../packaging/youtube-downloader.spec
#
# macOS: arm64 `YouTube Downloader.app` bundle (icon, Info.plist; signing and zip happen in CI).
# Windows: `YouTube Downloader/YouTube Downloader.exe`, no console window, icon, version info.
# APP_VERSION (env, e.g. "1.2.3") fills the version metadata; defaults to 0.0.0.
import os
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - SPECPATH is injected by PyInstaller
BACKEND = ROOT / "backend"
STATIC = BACKEND / "app" / "static"

APP_NAME = "YouTube Downloader"
ASSETS = ROOT / "packaging" / "assets"
_m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", os.environ.get("APP_VERSION", ""))
VERSION = tuple(int(g) for g in _m.groups()) if _m else (0, 0, 0)
VERSION_STR = ".".join(map(str, VERSION))


def windows_version_info():
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    quad = (*VERSION, 0)
    strings = {
        "CompanyName": "nicosmico",
        "FileDescription": APP_NAME,
        "FileVersion": VERSION_STR,
        "InternalName": APP_NAME,
        "OriginalFilename": f"{APP_NAME}.exe",
        "ProductName": APP_NAME,
        "ProductVersion": VERSION_STR,
    }
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=quad, prodvers=quad),
        kids=[
            StringFileInfo([StringTable("040904B0", [StringStruct(k, v) for k, v in strings.items()])]),
            VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
        ],
    )


if not (STATIC / "index.html").is_file():
    raise SystemExit(f"Angular build not found in {STATIC}: run `npm run build` in frontend/ first.")

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(BACKEND)],
    # `datas` pairs use the platform-independent (source, dest) tuple form: no `:`/`;` separator.
    datas=[(str(STATIC), "static"), *collect_data_files("certifi")],
    # uvicorn picks its loop/protocol implementations by name at runtime.
    hiddenimports=[*collect_submodules("uvicorn"), "truststore", "certifi"],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)  # noqa: F821
is_mac = sys.platform == "darwin"
is_win = sys.platform == "win32"
# macOS keeps the inner executable name stable (CFBundleExecutable); Windows shows it to users.
exe_name = "youtube-downloader" if is_mac else APP_NAME
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=exe_name,
    console=not is_win,
    icon=str(ASSETS / "icon.ico") if is_win else None,
    version=windows_version_info() if is_win else None,
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    name=exe_name if is_mac else APP_NAME,
)
if is_mac:
    app = BUNDLE(  # noqa: F821
        coll,
        name=f"{APP_NAME}.app",
        icon=str(ASSETS / "icon.icns"),
        bundle_identifier="io.github.nicosmico.youtube-downloader",
        version=VERSION_STR,
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": VERSION_STR,
            "LSMinimumSystemVersion": "13.0",
            "LSUIElement": False,
            "NSHighResolutionCapable": True,
        },
    )
