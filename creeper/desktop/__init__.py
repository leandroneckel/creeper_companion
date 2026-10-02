"""Integração com o sistema operacional.

Cada plataforma expõe as mesmas funções:
    window_flags_extra()      -> flags extras do Qt para a janela do creeper
    setup_window(widget)      -> ajustes após mostrar (todas as áreas de trabalho etc.)
    keep_on_top(widget)       -> reforça "sempre no topo"
    user_idle_seconds()       -> segundos sem teclado/mouse, ou None se não souber
    fullscreen_app_active()   -> True se algum app estiver em tela cheia
    autostart_enabled() / set_autostart(bool)
    needs_input_mask()        -> True se precisar de máscara para clicar através
    window_rects()            -> janelas abertas (só posição e tamanho), da de cima pra de baixo
"""
import sys

if sys.platform == "win32":
    from .windows import *  # noqa: F401,F403
elif sys.platform.startswith("linux"):
    from .linux import *  # noqa: F401,F403
else:
    from .fallback import *  # noqa: F401,F403
