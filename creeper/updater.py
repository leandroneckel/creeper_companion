"""Atualização: procura versão nova nas releases do GitHub, baixa, confere e troca o executável.

Só se troca sozinho quando roda como executável (PyInstaller); pelo código-fonte, só avisa.
No Windows um .exe aberto não pode ser apagado nem sobrescrito, mas pode ser renomeado: o atual
vira "<nome>.<pid>.old", o novo entra no lugar dele e é aberto, e o .old some quando o novo abrir.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import __version__

REPO = "leandroneckel/creeper_companion"
# CREEPER_UPDATE_URL troca o endereço (pra testar com um servidor local, um fork...)
LATEST_URL = os.environ.get("CREEPER_UPDATE_URL") or f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_NAMES = {"win32": "CreeperCompanion.exe", "linux": "CreeperCompanion-linux"}
# AppId do instalador (tools/instalador.iss): é por ele que o Windows reconhece o programa instalado. Nunca mude.
INSTALLER_GUID = "1160637A-01BF-4016-BE32-549DEE0D367C"
UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{{{INSTALLER_GUID}}}_is1"
FIRST_CHECK_MS = 60 * 1000        # deixa ele abrir em paz antes de olhar
CHECK_EVERY_MS = 6 * 3600 * 1000
TIMEOUT_MS = 30 * 1000            # sem chegar nada por esse tempo, desiste


def parse_version(text: str) -> tuple[int, int, int]:
    """"v1.2" -> (1, 2, 0). Texto que não começa com número vira (0, 0, 0)."""
    m = re.match(r"\s*[vV]?(\d+(?:\.\d+)*)", text or "")
    parts = [int(p) for p in m.group(1).split(".")] if m else []
    return tuple((parts + [0, 0, 0])[:3])


def newer(version: str, than: str) -> bool:
    return parse_version(version) > parse_version(than)


@dataclass
class Release:
    version: str                 # "1.2.0"
    notes: str                   # texto da release (markdown)
    page: str                    # página da release no GitHub
    url: str | None = None       # executável deste sistema (None: a release não tem)
    size: int = 0
    sha256: str | None = None    # o GitHub calcula sozinho para cada arquivo anexado


def parse_release(data: dict, platform: str = sys.platform) -> Release | None:
    tag = str(data.get("tag_name") or "")
    if data.get("draft") or data.get("prerelease") or parse_version(tag) == (0, 0, 0):
        return None
    release = Release(version=tag.strip().lstrip("vV"), notes=str(data.get("body") or "").strip(),
                      page=str(data.get("html_url") or f"https://github.com/{REPO}/releases"))
    for asset in data.get("assets") or []:
        if asset.get("name") == ASSET_NAMES.get(platform):
            digest = str(asset.get("digest") or "")
            release.url = asset.get("browser_download_url")
            release.size = int(asset.get("size") or 0)
            release.sha256 = digest[7:].lower() if digest.startswith("sha256:") else None
    return release


def target_file() -> Path | None:
    """O executável que a atualização troca, ou None quando roda pelo código-fonte."""
    if getattr(sys, "frozen", False) and sys.platform in ASSET_NAMES:
        return Path(sys.executable)
    return None


def can_self_update(release: Release) -> bool:
    return bool(release.url) and target_file() is not None


def looks_executable(path: Path) -> bool:
    """Confere a assinatura do arquivo (evita instalar uma página de erro no lugar do programa)."""
    magic = b"MZ" if sys.platform == "win32" else b"\x7fELF"
    try:
        with open(path, "rb") as f:
            return f.read(len(magic)) == magic
    except OSError:
        return False


def install(new: Path, target: Path) -> None:
    """Põe `new` no lugar de `target`, que pode estar rodando."""
    if sys.platform == "win32":
        old = target.with_name(f"{target.name}.{os.getpid()}.old")
        os.replace(target, old)
        try:
            os.replace(new, target)
        except OSError:
            os.replace(old, target)
            raise
    else:
        new.chmod(0o755)
        os.replace(new, target)   # no Linux o arquivo aberto continua valendo pra quem já está rodando


def cleanup(target: Path | None = None, partial: bool = True) -> None:
    """Apaga o que sobrou de atualizações: o executável antigo e (com `partial`) download pela metade."""
    target = target or target_file()
    if not target:
        return
    leftovers = list(target.parent.glob(target.name + ".*.old"))
    if partial:
        leftovers.append(target.with_name(target.name + ".new"))
    for path in leftovers:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass   # o antigo ainda está fechando: fica pra próxima


INSTALLER_CHOICE = (r"Software\CreeperCompanion", "AvisarVersaoNova")   # gravado pelo instalador


def take_installer_choice() -> bool | None:
    """O que marcaram no instalador em "Avisar quando sair versão nova" (lê e apaga: vale uma vez,
    depois manda o que estiver em Configurações). None se não veio do instalador."""
    if sys.platform != "win32":
        return None
    import winreg
    key_path, name = INSTALLER_CHOICE
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                            winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
            value = winreg.QueryValueEx(key, name)[0]
            winreg.DeleteValue(key, name)
            return bool(value)
    except OSError:
        return None


def sync_installed_version() -> None:
    """Se veio do instalador, corrige a versão que aparece em "Aplicativos instalados" (o instalador
    gravou a dele; as atualizações seguintes trocam só o executável)."""
    if sys.platform != "win32" or target_file() is None:
        return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0,
                            winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
            if winreg.QueryValueEx(key, "DisplayVersion")[0] != __version__:
                winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, __version__)
    except OSError:
        pass   # não foi instalado (é o .exe solto)


def relaunch(target: Path) -> None:
    """Abre o executável novo como um programa independente deste."""
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"   # senão ele se acha "filho" deste e usa os arquivos dele
    kwargs = {"cwd": str(target.parent), "env": env, "close_fds": True, "stdin": subprocess.DEVNULL,
              "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        if "LD_LIBRARY_PATH_ORIG" in env:
            env["LD_LIBRARY_PATH"] = env.pop("LD_LIBRARY_PATH_ORIG")
        else:
            env.pop("LD_LIBRARY_PATH", None)
        kwargs["start_new_session"] = True
    subprocess.Popen([str(target)], **kwargs)


class Updater(QObject):
    """Conversa com o GitHub, tudo no laço do Qt (sem threads).

    on_result(release, erro, manual): `release` só vem quando é mais nova que esta versão.
    """

    def __init__(self, on_result, parent=None):
        super().__init__(parent)
        self.on_result = on_result
        self.net = QNetworkAccessManager(self)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check)
        self.downloading: QNetworkReply | None = None
        self._cancelled = False

    def start(self) -> None:
        if not self.timer.isActive():
            self.timer.start(FIRST_CHECK_MS)

    def stop(self) -> None:
        self.timer.stop()

    def _request(self, url: str) -> QNetworkRequest:
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", f"CreeperCompanion/{__version__}".encode())
        req.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.NoLessSafeRedirectPolicy)
        req.setTransferTimeout(TIMEOUT_MS)
        return req

    def check(self, manual: bool = False) -> None:
        if self.timer.isActive():
            self.timer.setInterval(CHECK_EVERY_MS)   # a primeira foi logo depois de abrir
        req = self._request(LATEST_URL)
        req.setRawHeader(b"Accept", b"application/vnd.github+json")
        reply = self.net.get(req)
        reply.finished.connect(lambda: self._checked(reply, manual))

    def _checked(self, reply: QNetworkReply, manual: bool) -> None:
        reply.deleteLater()
        release, error = None, ""
        if reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) == 404:
            pass   # ainda não tem nenhuma versão publicada
        elif reply.error() != QNetworkReply.NoError:
            error = reply.errorString()
        else:
            try:
                release = parse_release(json.loads(bytes(reply.readAll()).decode("utf-8")))
            except (ValueError, TypeError, AttributeError):
                error = "o GitHub respondeu algo estranho"
        if release and not newer(release.version, __version__):
            release = None
        self.on_result(release, error, manual)

    def download(self, release: Release, on_progress, on_done) -> None:
        """Baixa o executável novo para "<nome>.new", ao lado do atual, e confere.

        on_progress(recebido, total); on_done(arquivo, erro): erro "cancelado" se cancel() foi chamado.
        """
        target = target_file()
        part = target.with_name(target.name + ".new")
        try:
            out = open(part, "wb")
        except OSError as exc:
            on_done(None, f"não consegui gravar na pasta do programa ({exc.strerror or exc})")
            return
        digest = hashlib.sha256()
        failure: list[str] = []
        reply = self.net.get(self._request(release.url))
        self.downloading = reply
        self._cancelled = False

        def write() -> None:
            chunk = bytes(reply.readAll())
            if failure or not chunk:
                return
            try:
                out.write(chunk)
            except OSError as exc:
                failure.append(f"não consegui gravar o arquivo ({exc.strerror or exc})")
                reply.abort()
                return
            digest.update(chunk)

        def finished() -> None:
            write()
            out.close()
            reply.deleteLater()
            self.downloading = None
            if self._cancelled:
                error = "cancelado"
            elif failure:
                error = failure[0]
            elif reply.error() != QNetworkReply.NoError:
                error = reply.errorString()
            elif release.size and part.stat().st_size != release.size:
                error = "o arquivo veio incompleto"
            elif release.sha256 and digest.hexdigest() != release.sha256:
                error = "o arquivo veio corrompido"
            elif not looks_executable(part):
                error = "o arquivo baixado não é um programa"
            else:
                on_done(part, "")
                return
            try:
                part.unlink(missing_ok=True)
            except OSError:
                pass
            on_done(None, error)

        reply.readyRead.connect(write)
        reply.downloadProgress.connect(lambda got, total: on_progress(got, total if total > 0 else release.size))
        reply.finished.connect(finished)

    def cancel(self) -> None:
        if self.downloading:
            self._cancelled = True
            self.downloading.abort()
