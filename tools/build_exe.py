"""Gera o executável (um arquivo só) com o PyInstaller e, no Windows, o instalador com o Inno Setup.

Uso:  python tools/build_exe.py
Sai em dist/: CreeperCompanion.exe (o que a atualização automática baixa) e CreeperCompanion-Setup.exe
(o que as pessoas baixam na primeira vez); no Linux, CreeperCompanion-linux. A versão é a de
creeper/__init__.py.

Precisa do PyInstaller (pip install -r requirements-dev.txt) e, pro instalador, do Inno Setup 6
(winget install JRSoftware.InnoSetup). Assinatura digital (opcional): com um certificado de assinatura
de código instalado no Windows, defina CREEPER_CERTIFICADO com a impressão digital (thumbprint) dele.
"""
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # só pra desenhar o ícone e as imagens

from creeper import __version__, updater  # noqa: E402

BUILD = ROOT / "build"
DIST = ROOT / "dist"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
SETUP_NAME = "CreeperCompanion-Setup.exe"
TIMESTAMP_URL = "http://timestamp.digicert.com"


def exe_path() -> Path:
    """Onde o executável deste sistema vai parar (o nome é o que o atualizador procura na release)."""
    return DIST / updater.ASSET_NAMES[sys.platform]


def setup_path() -> Path:
    return DIST / SETUP_NAME


def _qt():
    from PySide6.QtGui import QGuiApplication
    return QGuiApplication.instance() or QGuiApplication([])


def make_icon(path: Path) -> None:
    """.ico com a cabeça do creeper em vários tamanhos, cada um ampliado sem borrar o pixel art."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from creeper.art import sprite
    from creeper.art.sprite import Pose

    _app = _qt()  # noqa: F841
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


def make_installer_images() -> None:
    """Imagens do assistente de instalação, em 100% e 200%: o creeper em pé na grama (lateral)
    e a cabeça dele (canto de cima)."""
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QImage, QPainter
    from creeper.art import sprite
    from creeper.art.sprite import Pose

    _app = _qt()  # noqa: F841
    body = sprite.render(Pose(eyes="glint"))
    head = sprite.render_head(Pose(eyes="glint"))
    for k, suffix in ((1, ""), (2, "-2x")):
        w, h, s = 164 * k, 314 * k, 3 * k
        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(QColor("#160A1C"))
        p = QPainter(img)
        ground = h - 70 * k
        p.fillRect(QRect(0, ground, w, 8 * k), QColor("#5D9C3A"))           # grama
        p.fillRect(QRect(0, ground + 8 * k, w, h - ground), QColor("#6B4A2E"))   # terra
        for i in range(0, w, 12 * k):   # pontinhos de grama caindo na terra
            p.fillRect(QRect(i + (i // (12 * k) % 2) * 4 * k, ground + 8 * k, 4 * k, 4 * k), QColor("#4A7F2D"))
        scaled = body.scaled(body.width() * s, body.height() * s, Qt.IgnoreAspectRatio, Qt.FastTransformation)
        p.drawImage((w - scaled.width()) // 2, ground - scaled.height(), scaled)
        p.end()
        img.save(str(BUILD / f"instalador-grande{suffix}.png"))

        small = QImage(55 * k, 58 * k, QImage.Format_ARGB32)
        small.fill(Qt.transparent)
        p = QPainter(small)
        face = head.scaled(48 * k, 48 * k, Qt.IgnoreAspectRatio, Qt.FastTransformation)
        p.drawImage((small.width() - face.width()) // 2, (small.height() - face.height()) // 2, face)
        p.end()
        small.save(str(BUILD / f"instalador-pequeno{suffix}.png"))


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


def find_iscc() -> Path | None:
    """O compilador do Inno Setup (instalado pro usuário pelo winget, ou pra todos)."""
    candidates = [shutil.which("ISCC")]
    if os.environ.get("LOCALAPPDATA"):
        candidates.append(Path(os.environ["LOCALAPPDATA"], "Programs", "Inno Setup 6", "ISCC.exe"))
    for var in ("ProgramFiles(x86)", "ProgramFiles"):
        if os.environ.get(var):
            candidates.append(Path(os.environ[var], "Inno Setup 6", "ISCC.exe"))
    return next((Path(c) for c in candidates if c and Path(c).exists()), None)


def sign(path: Path) -> None:
    """Assina com o certificado CREEPER_CERTIFICADO (thumbprint, guardado no Windows), se houver."""
    thumb = os.environ.get("CREEPER_CERTIFICADO", "").replace(" ", "").upper()
    if not thumb:
        return
    script = f"""
$cert = Get-ChildItem Cert:\\CurrentUser\\My, Cert:\\LocalMachine\\My | Where-Object Thumbprint -eq '{thumb}' |
    Select-Object -First 1
if (-not $cert) {{ Write-Error 'Certificado {thumb} não encontrado'; exit 1 }}
$r = Set-AuthenticodeSignature -LiteralPath '{path}' -Certificate $cert -HashAlgorithm SHA256 `
    -TimestampServer '{TIMESTAMP_URL}'
if ($r.SignerCertificate.Thumbprint -ne '{thumb}') {{ Write-Error $r.StatusMessage; exit 1 }}
"""
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], check=True)
    print(f"Assinado: {path.name}")


def build_installer() -> Path:
    iscc = find_iscc()
    if not iscc:
        raise FileNotFoundError("Inno Setup 6 não encontrado (winget install JRSoftware.InnoSetup)")
    make_installer_images()
    subprocess.run([str(iscc), "/Q", f"/DAppVersion={__version__}", f"/DAppGuid={updater.INSTALLER_GUID}",
                    str(ROOT / "tools" / "instalador.iss")], check=True, cwd=ROOT)
    out = setup_path()
    sign(out)
    print(f"Pronto: {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return out


def build(installer: bool = True) -> list[Path]:
    """Gera o executável e (no Windows, com `installer`) o instalador. Devolve os arquivos gerados."""
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
    sign(out)
    print(f"Pronto: {out} ({out.stat().st_size / 1e6:.1f} MB)")
    made = [out]
    if installer and sys.platform == "win32":
        made.append(build_installer())
    return made


if __name__ == "__main__":
    want_installer = sys.platform == "win32" and find_iscc() is not None
    if sys.platform == "win32" and not want_installer:
        print("Inno Setup 6 não encontrado: gerando só o executável (winget install JRSoftware.InnoSetup).")
    build(installer=want_installer)
