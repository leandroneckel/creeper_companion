"""Janela "versão nova": mostra o que mudou e pergunta se pode atualizar."""
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextBrowser, QVBoxLayout

from .. import __version__, updater


class UpdateDialog(QDialog):
    def __init__(self, app, release: updater.Release):
        super().__init__(None, Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint | Qt.WindowStaysOnTopHint)
        self.app = app
        self.release = release
        self.busy = False
        self.setWindowTitle("Versão nova do Creeper Companion")
        self.setWindowIcon(app.tray.icon())
        self.setMinimumWidth(440)

        title = QLabel(f"<b>Saiu a versão {release.version}!</b> Você está com a {__version__}.")
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(release.notes or "_Sem descrição._")
        notes.setMinimumHeight(170)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.hide()
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setOpenExternalLinks(True)

        self.skip_btn = QPushButton("Pular esta versão")
        self.later_btn = QPushButton("Agora não")
        self.go_btn = QPushButton("Atualizar agora" if updater.can_self_update(release) else "Abrir página da versão")
        self.go_btn.setDefault(True)
        self.skip_btn.clicked.connect(self._skip)
        self.later_btn.clicked.connect(self.reject)
        self.go_btn.clicked.connect(self._go)

        buttons = QHBoxLayout()
        buttons.addWidget(self.skip_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.later_btn)
        buttons.addWidget(self.go_btn)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(QLabel("O que mudou:"))
        layout.addWidget(notes, 1)
        layout.addWidget(self.bar)
        layout.addWidget(self.status)
        layout.addLayout(buttons)

        if updater.target_file() is None:
            self._say("Você está rodando pelo código-fonte: pra atualizar, use <code>git pull</code>.")
        elif not release.url:
            self._say("Essa versão ainda não tem o programa pronto pro seu sistema. Dá uma olhada na página dela.")
        else:
            self._say("Seu creeper, o nível e tudo o que ele ganhou continuam do jeitinho que estão.")

    def _say(self, html: str) -> None:
        self.status.setText(html)

    def _skip(self) -> None:
        self.app.skip_update(self.release)
        self.accept()

    def _go(self) -> None:
        if not updater.can_self_update(self.release):
            QDesktopServices.openUrl(QUrl(self.release.page))
            self.accept()
            return
        self.busy = True
        self.skip_btn.setEnabled(False)
        self.go_btn.setEnabled(False)
        self.later_btn.setText("Cancelar")
        self.bar.setRange(0, 0)
        self.bar.show()
        self._say("Baixando...")
        self.app.updater.download(self.release, self._progress, self._downloaded)

    def _progress(self, got: int, total: int) -> None:
        if total > 0:
            self.bar.setRange(0, total)
            self.bar.setValue(got)
            self._say(f"Baixando... {got / 1e6:.1f} de {total / 1e6:.1f} MB")

    def _downloaded(self, path, error: str) -> None:
        if error == "cancelado":
            return   # a janela já está fechando
        if path is None:
            self._failed(error)
            return
        self.later_btn.setEnabled(False)
        self._say("Pronto! Reabrindo com a versão nova...")
        QTimer.singleShot(600, lambda: self._install(path))

    def _install(self, path) -> None:
        error = self.app.finish_update(path)   # se der certo, o app fecha e o novo abre
        if error:
            self._failed(error)

    def _failed(self, error: str) -> None:
        self.busy = False
        self.bar.hide()
        self.skip_btn.setEnabled(True)
        self.go_btn.setEnabled(True)
        self.go_btn.setText("Tentar de novo")
        self.later_btn.setEnabled(True)
        self.later_btn.setText("Agora não")
        self._say(f"Não deu pra atualizar: {error}. Tenta de novo mais tarde ou baixe pela "
                  f'<a href="{self.release.page}">página da versão</a>.')

    def reject(self) -> None:
        """"Agora não", "Cancelar", Esc ou o X da janela."""
        if self.busy:
            self.busy = False
            self.app.updater.cancel()
        self.app.snooze_update()
        super().reject()
