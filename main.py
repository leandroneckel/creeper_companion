"""Creeper Companion: um creeper de estimação que mora na sua tela."""
import getpass
import os
import sys


def main() -> int:
    if (sys.platform.startswith("linux") and os.environ.get("XDG_SESSION_TYPE") == "wayland"
            and "QT_QPA_PLATFORM" not in os.environ):
        # Wayland não deixa apps ficarem "sempre no topo" nem em todas as áreas de
        # trabalho; via XWayland (xcb) dá.
        os.environ["QT_QPA_PLATFORM"] = "xcb"

    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import QApplication

    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setApplicationName("Creeper Companion")

    # Só uma instância: se já estiver aberto, pede pra ele aparecer e sai.
    key = f"creeper-companion-{getpass.getuser()}"
    probe = QLocalSocket()
    probe.connectToServer(key)
    if probe.waitForConnected(300):
        probe.write(b"show")
        probe.flush()
        probe.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(key)
    server = QLocalServer()
    server.listen(key)

    from creeper.app import CompanionApp
    companion = CompanionApp(qapp)
    companion.instance_server = server

    def on_connection():
        conn = server.nextPendingConnection()
        if conn:
            conn.disconnected.connect(conn.deleteLater)
        companion.show_from_tray()

    server.newConnection.connect(on_connection)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
