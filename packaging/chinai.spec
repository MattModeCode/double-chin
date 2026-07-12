# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ChinAI.app — a self-contained macOS desktop app.

Bundles Python + torch + the Chatterbox TTS engine + the Studio SPA into
one relocatable .app. Model weights are NOT baked in by default: they are
fetched once from Hugging Face on first "Generate" and cached under
~/.cache/huggingface, same as running from source. This keeps the bundle
a few GB instead of ~8 GB; see docs/design.md for the tradeoff.

Build with: bash packaging/build_app.sh
(equivalent to: pyinstaller packaging/chinai.spec --noconfirm, run from the repo root)
"""

import shutil
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata

REPO_ROOT = Path(SPECPATH).resolve().parent
STATIC_DIR = REPO_ROOT / "src" / "chinai" / "studio" / "static"
ICON_PATH = REPO_ROOT / "assets" / "brand" / "ChinAI.icns"
ENTRY_SCRIPT = REPO_ROOT / "src" / "chinai" / "desktop.py"

datas = []
binaries = []
hiddenimports = []

# Heavy trees whose C extensions / data files PyInstaller can't infer from
# imports alone. This is the fragile step of the build — if the bundled app
# fails at runtime with a missing-module error, add that package here.
for package in (
    "torch",
    "torchaudio",
    "chatterbox",
    "transformers",
    "resemblyzer",
    "perth",
    "diffusers",
):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# transformers and diffusers check their own dependency versions at import
# time via importlib.metadata.version(...), which needs each package's
# *.dist-info directory on disk — PyInstaller's static import analysis can't
# see that dynamic lookup, so it never bundles that metadata on its own.
# Missing metadata surfaces at runtime as
# `PackageNotFoundError: No package metadata was found for <pkg>`, not as an
# import error, so it wasn't caught by the "missing-module" note above. See
# transformers/dependency_versions_check.py and
# diffusers/dependency_versions_check.py for the exact packages each checks.
for package in (
    "requests",
    "filelock",
    "numpy",
    "packaging",
    "tqdm",
    "regex",
    "tokenizers",
    "huggingface-hub",
    "safetensors",
    "pyyaml",
):
    datas += copy_metadata(package)

# The Studio single-page app: studio/app.py resolves its static directory as
# `Path(__file__).parent / "static"`, so it must land at this exact path
# inside the bundle.
datas += [(str(STATIC_DIR), "chinai/studio/static")]

# ffmpeg is needed to decode .m4a/.mp3 enrolment recordings (torchaudio has
# no bundled AAC decoder). Bundle whatever the build machine has on PATH.
ffmpeg_path = shutil.which("ffmpeg")
if ffmpeg_path:
    binaries += [(ffmpeg_path, ".")]

a = Analysis(
    [str(ENTRY_SCRIPT)],
    pathex=[str(REPO_ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ChinAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ICON_PATH),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="ChinAI",
)

app = BUNDLE(
    coll,
    name="ChinAI.app",
    icon=str(ICON_PATH),
    bundle_identifier="com.mashuai.chinai",
    info_plist={
        "CFBundleName": "ChinAI",
        "CFBundleDisplayName": "ChinAI",
        "CFBundleIdentifier": "com.mashuai.chinai",
        "CFBundleShortVersionString": "0.1.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "12.0",
        "NSHumanReadableCopyright": "ChinAI — local voice cloning, entirely on your machine.",
    },
)
