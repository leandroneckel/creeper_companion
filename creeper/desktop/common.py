import sys
from pathlib import Path


def launch_command() -> list[str]:
    """Comando para abrir o companion (usado no "iniciar com o sistema")."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    main = Path(__file__).resolve().parent.parent.parent / "main.py"
    exe = Path(sys.executable)
    if sys.platform == "win32":
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.exists():
            exe = pythonw
    return [str(exe), str(main)]
