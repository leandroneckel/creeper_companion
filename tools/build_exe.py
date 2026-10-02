"""Gera o executável (um arquivo só) com o PyInstaller.

Uso:  python tools/build_exe.py
Sai em dist/CreeperCompanion.exe (Windows) ou dist/CreeperCompanion-linux (Linux), com a versão
que está em creeper/__init__.py. Precisa do PyInstaller:  pip install -r requirements-dev.txt
"""
import os
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # só pra desenhar o ícone

from creeper import __version__, updater  # noqa: E402

BUILD = ROOT / "build"
DIST = ROOT / "dist"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def exe_path() -> Path:
    """Onde o executável deste sistema vai parar (o nome é o que o atualizador procura na release)."""
    return DIST / updater.ASSET_NAMES[sys.platform]


def make_icon(path: Path) -> None:
    """.ico com a cabeça do creeper em vários tamanhos, cada um ampliado sem borrar o pixel art."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PySide6.QtGui import QGuiApplication
    from creeper.art import sprite
    from creeper.art.sprite import Pose

    _app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    head = sprite.render_head(Pose(eyes="glint"))
    pngs = []
    for size in ICON_SIZES:
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.WriteOnly)
        head.scaled(size, size, Qt.IgnoreAspectRatio, Qt.FastTransformation).save(buf, "PNG")
        buf.close()
        pngs.append((size, bytes(data)))
    offset = 6 + 16 * len(pngs)
    entries, blobs = b"", b""
    for size, png in pngs:   # entradas com PNG dentro (vale desde o Windows Vista)
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), offset + len(blobs))
        blobs += png
    path.write_bytes(struct.pack("<HHH", 0, 1, len(pngs)) + entries + blobs)


def make_version_file(path: Path) -> None:
    """Propriedades do .exe (nome e versão que aparecem no Gerenciador de Tarefas e em Detalhes)."""
    nums = (*updater.parse_version(__version__), 0)
    path.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041604B0', [
      StringStruct('CompanyName', 'Leandro Neckel'),
      StringStruct('FileDescription', 'Creeper Companion'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'CreeperCompanion'),
      StringStruct('LegalCopyright', 'Copyright (c) 2026 Leandro Neckel. Licença MIT.'),
      StringStruct('OriginalFilename', 'CreeperCompanion.exe'),
      StringStruct('ProductName', 'Creeper Companion'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1046, 1200])])
  ]
)
""", encoding="utf-8")


def build() -> Path:
    if sys.platform not in updater.ASSET_NAMES:
        sys.exit(f"Sem executável para {sys.platform} (só Windows e Linux).")
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.exit("Falta o PyInstaller:  pip install -r requirements-dev.txt")
    BUILD.mkdir(exist_ok=True)
    out = exe_path()
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
           "--log-level", "WARN", "--name", out.stem if sys.platform == "win32" else out.name,
           "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller"), "--specpath", str(BUILD),
           "--add-data", f"{ROOT / 'content'}{os.pathsep}content"]
    if sys.platform == "win32":
        make_icon(BUILD / "creeper.ico")
        make_version_file(BUILD / "versao.txt")
        cmd += ["--icon", str(BUILD / "creeper.ico"), "--version-file", str(BUILD / "versao.txt")]
    cmd.append(str(ROOT / "main.py"))
    print(f"Gerando {out.name} {__version__}...")
    subprocess.run(cmd, check=True, cwd=ROOT)
    print(f"Pronto: {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return out


if __name__ == "__main__":
    build()
