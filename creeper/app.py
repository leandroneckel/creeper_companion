"""Liga tudo: necessidades, comportamento, janela, bandeja, lembretes e salvamento."""
import time
from datetime import datetime

from PySide6.QtCore import QElapsedTimer, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QInputDialog, QMenu, QSystemTrayIcon

from . import __version__, desktop, surfaces, updater
from .ball import Ball
from .config import Settings, load_save, write_save
from .content import load_content
from .needs import Needs
from .pet import Pet
from .progress import Progress
from .sound.player import Sounds
from .ui import menus
from .ui.pet_window import PetWindow
from .ui.ball_window import BallWindow
from .ui.toast import Toast
from .ui.tray import Tray
from .ui.update_dialog import UpdateDialog

FRAME_MS = 33
CARE_CONFIRM_SECONDS = 10 * 60   # quanto tempo dá pra apertar "Fiz!" depois de um lembrete
UPDATE_SNOOZE_SECONDS = 24 * 3600   # "agora não": pergunta de novo no dia seguinte
CARE_REMINDERS = {"lembrete_agua": "agua", "lembrete_pausa": "pausa"}


def format_elapsed(seconds: float) -> str:
    days = int(seconds // 86400)
    if days >= 1:
        return f"{days} dia" + ("s" if days > 1 else "")
    hours = int(seconds // 3600)
    if hours >= 1:
        return f"{hours} hora" + ("s" if hours > 1 else "")
    minutes = max(1, int(seconds // 60))
    return f"{minutes} minuto" + ("s" if minutes > 1 else "")


class CompanionApp(QObject):
    def __init__(self, qapp):
        super().__init__()
        self.qapp = qapp
        menus.install_style(qapp)

        save = load_save()
        self.first_run = not save
        self.prev_version = save.get("app_version")   # versão que salvou da última vez
        self.settings = Settings.from_dict(save.get("settings"))
        self.items, self.lines, self.achievements = load_content()
        pet_data = save.get("pet") or {}
        self.needs = Needs.from_dict(pet_data.get("needs"))
        self.progress = Progress.from_dict(pet_data.get("progress"), self.items, self.achievements)
        saved_at = save.get("saved_at")
        self.away = max(0.0, time.time() - saved_at) if saved_at else 0.0
        self.needs.apply_offline(self.away, self.settings.needs_speed)

        self.pet = Pet(self.settings, self.items, self.lines, self.needs, self.progress)
        self.pet.say = self.on_say
        self.pet.on_achievement = self.on_achievement
        self._place_pet(pet_data.get("x"))
        self.care_pending: tuple[str, float] | None = None   # ("agua" | "pausa", até quando)
        self._achievement_queue: list[dict] = []

        self.has_tray = QSystemTrayIcon.isSystemTrayAvailable()
        self.in_tray = self.has_tray and not (save.get("window") or {}).get("visible", True)
        self.fs_hidden = False
        self._popup: QMenu | None = None
        self._last_notify = -1e9
        self._tray_hint_shown = False
        self._tray_click = None   # o que fazer se clicarem no último aviso da bandeja

        self.instance_server = None   # main.py preenche: é fechado antes de abrir a versão nova
        self.update_offer: updater.Release | None = None
        self._update_announce = False
        self._update_snooze_until = 0.0
        self._update_dialog: UpdateDialog | None = None
        self.updater = updater.Updater(self.on_update_result, self)
        updater.cleanup()
        QTimer.singleShot(15000, lambda: updater.cleanup(partial=False))   # o antigo pode demorar a fechar
        if self.settings.check_updates:
            self.updater.start()

        self.sounds = Sounds(self.settings, self)
        self.pet.sfx = self.play_sound
        self.pet.sfx_stop = self.sounds.stop
        QTimer.singleShot(500, self.sounds.load)  # o que faltar no cache é gerado em segundo plano

        self.window = PetWindow(self)
        self.toast = Toast()
        self.ball = Ball()
        self.ball.on_bounce = lambda strength: self.play_sound("quique", 0.3 + 0.7 * strength)
        self.pet.ball = self.ball
        self.ball_window = BallWindow(self.ball, self.on_ball_thrown)
        self.tray = Tray(self)
        self.tray.messageClicked.connect(self._on_tray_message)
        self.tray.show()

        now = time.monotonic()
        self.last_water = now
        self.last_sleep_reminder = -1e9
        self.active_streak = 0.0
        self._last_care = now

        self._clock = QElapsedTimer()
        self._clock.start()
        self._last_ms = 0
        self._timers = []
        for ms, slot in ((FRAME_MS, self.tick), (2000, self.slow_tick), (30000, self.care_tick), (60000, self.save),
                         (1000, self.refresh_platforms)):
            timer = QTimer(self)
            if ms == FRAME_MS:
                timer.setTimerType(Qt.PreciseTimer)  # o timer padrão do Windows arredonda pra ~21 fps
            timer.timeout.connect(slot)
            timer.start(ms)
            self._timers.append(timer)

        qapp.aboutToQuit.connect(self.save)
        self.apply_visibility()
        QTimer.singleShot(1200, self.greet)

    # ---- posição / mundo -------------------------------------------------
    def _screen_for(self, x: float, y: float):
        screen = QGuiApplication.screenAt(QPoint(int(x), int(y) - 10))
        if screen:
            return screen

        def dist(s):
            g = s.availableGeometry()
            dx = max(g.left() - x, 0, x - g.right())
            dy = max(g.top() - y, 0, y - g.bottom() - 1)
            return dx * dx + dy * dy
        return min(QGuiApplication.screens(), key=dist)

    def _place_pet(self, x) -> None:
        screen = QGuiApplication.primaryScreen()
        if x is not None:
            for s in QGuiApplication.screens():
                g = s.availableGeometry()
                if g.left() <= x <= g.right():
                    screen = s
                    break
            else:
                x = None
        geo = screen.availableGeometry()
        self.pet.x = float(x if x is not None else geo.center().x())
        self.pet.y = float(geo.bottom() + 1)
        self._update_world()

    def _update_world(self) -> None:
        pet = self.pet
        if pet.state == "exercise" and pet.data.get("kind") == "gato":
            return
        geo = self._screen_for(pet.x, pet.y).availableGeometry()
        pet.world = (geo.left(), geo.top(), geo.right() + 1, geo.bottom() + 1)

    # ---- laços -----------------------------------------------------------
    def tick(self) -> None:
        ms = self._clock.elapsed()
        dt = (ms - self._last_ms) / 1000.0
        self._last_ms = ms
        pos = QCursor.pos()
        self.pet.cursor = (pos.x(), pos.y())
        self._update_world()
        self.pet.update(dt)
        self.window.frame()
        if self.ball.active:
            geo = self._screen_for(self.ball.x, self.ball.y).availableGeometry()
            self.ball.world = (geo.left(), geo.top(), geo.right() + 1, geo.bottom() + 1)
            self.ball.update(min(dt, 0.05))
        self.ball_window.sync(self.window.isVisible())
        self._adapt_frame_rate()

    def _adapt_frame_rate(self) -> None:
        """30 fps quando ele está se mexendo; bem menos quando está parado."""
        pet, win = self.pet, self.window
        moving = (pet.state in ("walk", "exercise", "hiss", "dragged", "fall", "eat", "drink", "exploded",
                                "leap", "come", "fetch", "hide")
                  or pet.jump > 0 or pet.squash > 0 or pet.size != pet.size_target or win.dragging
                  or (self.ball.active and not self.ball.resting))
        if not win.isVisible():
            ms = 250
        elif moving or win.hover_since is not None:
            ms = FRAME_MS
        elif pet.particles:
            ms = 66
        else:
            ms = 100
        timer = self._timers[0]
        if timer.interval() != ms:
            timer.setInterval(ms)

    def slow_tick(self) -> None:
        if self.settings.hide_fullscreen:
            fs = desktop.fullscreen_app_active()
            if fs != self.fs_hidden:
                self.fs_hidden = fs
                self.apply_visibility()
        if self.window.isVisible() and not self.window.dragging:
            desktop.keep_on_top(self.window)
            if self.ball_window.isVisible():
                desktop.keep_on_top(self.ball_window)
        self.tray.refresh()

    def refresh_platforms(self) -> None:
        """Bordas das janelas abertas onde ele pode subir (se já aprendeu e está ligado)."""
        pet = self.pet
        if self.settings.climb and self.progress.knows("janelas") and self.window.isVisible():
            pet.platforms = surfaces.platforms(surfaces.windows())
        else:
            pet.platforms = []
        timer = self._timers[4]
        ms = 300 if pet.perch else 1000   # em cima de uma janela, confere mais vezes (ela pode mexer)
        if timer.interval() != ms:
            timer.setInterval(ms)

    def _bring_to_screen(self, x: float, y: float) -> None:
        """Se (x, y) está em outro monitor, ele 'aparece' lá (não dá pra andar entre telas)."""
        target = self._screen_for(x, y)
        if target == self._screen_for(self.pet.x, self.pet.y):
            return
        geo = target.availableGeometry()
        pet = self.pet
        if pet.state not in ("idle", "walk", "sit", "sleep", "fetch", "come"):
            return
        pet.perch = None
        pet.set_state("idle", dur=2)
        pet.x = float(max(geo.left() + 80, min(geo.right() - 80, x)))
        pet.y = float(geo.bottom() + 1)
        self._update_world()
        pet.sfx("poof")

    def care_tick(self) -> None:
        """XP pelo tempo junto e lembretes pra você: água, pausas e hora de dormir."""
        now = time.monotonic()
        dt = now - self._last_care
        self._last_care = now
        idle = desktop.user_idle_seconds()
        self.pet.user_idle(idle)
        active = idle is None or idle < 120
        self.progress.tick(dt, active, self.needs)
        if active:
            self.active_streak += dt
        elif idle > 300:
            self.active_streak = 0.0
            self.last_water = max(self.last_water, now - self.settings.water_minutes * 60 + 300)
        if not active:
            return
        s = self.settings
        reminder = None
        if s.remind_water and now - self.last_water >= s.water_minutes * 60:
            self.last_water = now
            reminder = "lembrete_agua"
        elif s.remind_break and self.active_streak >= s.break_minutes * 60:
            self.active_streak = 0.0
            reminder = "lembrete_pausa"
        elif s.remind_sleep and datetime.now().hour < 5 and now - self.last_sleep_reminder > 30 * 60:
            self.last_sleep_reminder = now
            reminder = "lembrete_dormir"
        if reminder in CARE_REMINDERS:
            self.care_pending = (CARE_REMINDERS[reminder], now + CARE_CONFIRM_SECONDS)
        if reminder and self.pet.line(reminder, "reminder"):
            self.play_sound("lembrete")

    def pending_care(self) -> str | None:
        """"agua" ou "pausa" se ainda dá pra apertar "Fiz!" no último lembrete."""
        if self.care_pending and time.monotonic() < self.care_pending[1]:
            return self.care_pending[0]
        return None

    def confirm_care(self) -> None:
        kind = self.pending_care()
        self.care_pending = None
        self.window.clear_sticky()
        if kind:
            self.pet.self_care(kind)

    def open_present(self) -> None:
        self.pet.open_present()

    # ---- brincadeiras ----------------------------------------------------
    def call_pet(self) -> None:
        """'Vem cá!': ele corre até o mouse (aparece no monitor certo, se precisar)."""
        if not self.progress.knows("chamar"):
            return
        if self.in_tray:
            self.show_from_tray()
        pos = QCursor.pos()
        self._bring_to_screen(pos.x(), pos.y())
        self.pet.call(pos.x())

    def toggle_ball(self) -> None:
        if self.ball.active:
            self.pet.end_ball()
            return
        if not self.progress.knows("bolinha") or not self.pet.can_interact() or self.pet.busy():
            return
        pet = self.pet
        self.ball.place(pet.x + pet.facing * (pet.sprite_w * 0.6 + 14), pet.y - pet.sprite_h * 0.6)
        self.ball.thrown_from = pet.x
        pet.start_ball()

    def on_ball_thrown(self) -> None:
        self._bring_to_screen(self.ball.x, self.ball.y)
        self.pet.fetch()

    def start_hide(self) -> None:
        if self.progress.knows("esconde"):
            if self.ball.active:
                self.pet.end_ball()
            self.pet.hide_and_seek(surfaces.windows())

    def set_outfit(self, kind: str, value) -> None:
        """Guarda-roupa: kind = "chapeu" | "cor" | "rastro" | "carregado"."""
        self.pet.wear(kind, value)
        self.save()

    # ---- conquistas ------------------------------------------------------
    def on_achievement(self, achievement: dict) -> None:
        self._achievement_queue.append(achievement)
        self._flush_achievements()

    def _flush_achievements(self) -> None:
        if self.fs_hidden:
            return  # espera o jogo/vídeo em tela cheia acabar
        while self._achievement_queue:
            ach = self._achievement_queue.pop(0)
            if self.window.isVisible():
                self.toast.show_achievement(ach, self.window.screen())
                self.play_sound("conquista")
            elif self.settings.notifications:
                self.notify("Conquista feita!", ach["nome"], 6000)

    # ---- fala e sons -----------------------------------------------------
    def play_sound(self, name: str, volume: float = 1.0) -> None:
        if self.window.isVisible():  # na bandeja ou escondido por tela cheia, fica quieto
            self.sounds.play(name, volume)

    def on_say(self, text: str, kind: str = "chat") -> None:
        if self.window.isVisible():
            care = self.pending_care() if kind == "reminder" else None
            if care:
                self.window.show_bubble(text, action=care)
            elif kind in ("chat", "need") and self.window.sticky_active():
                pass  # não cobre o lembrete com o botão "Fiz!" com conversa fiada
            else:
                self.window.show_bubble(text)
            return
        if (kind in ("need_critical", "reminder") and self.settings.notifications
                and self.in_tray and not self.fs_hidden):
            now = time.monotonic()
            if kind == "reminder" or now - self._last_notify > 600:
                self._last_notify = now
                self.notify(self.settings.name, text, 7000)

    def notify(self, title: str, text: str, ms: int = 7000, on_click=None) -> None:
        """Aviso da bandeja do sistema; `on_click` roda se clicarem nele."""
        self._tray_click = on_click
        self.tray.showMessage(title, text, self.tray.icon(), ms)

    def _on_tray_message(self) -> None:
        click, self._tray_click = self._tray_click, None
        if click:
            click()

    def tell(self, text: str) -> None:
        """Resposta a algo que você pediu: no balão, ou na bandeja se ele estiver lá."""
        if self.window.isVisible():
            self.window.show_bubble(text)
        else:
            self.notify(self.settings.name, text, 6000)

    def greet(self) -> None:
        pet = self.pet
        if self.first_run:
            pet.line("primeira_vez")
        elif self.prev_version and updater.newer(__version__, self.prev_version):
            pet.line("atualizado", versao=__version__)
        elif self.away > 24 * 3600:
            pet.line("voltou_longe", tempo=format_elapsed(self.away))
        elif self.away > 4 * 3600 or self.away < 60:
            hour = datetime.now().hour
            period = ("madrugada" if hour < 5 else "manha" if hour < 12
                      else "tarde" if hour < 18 else "noite")
            pet.line(f"saudacao_{period}")
        else:
            pet.line("voltou_curto")

    # ---- visibilidade ----------------------------------------------------
    def apply_visibility(self) -> None:
        should = not self.in_tray and not self.fs_hidden
        if should and not self.window.isVisible():
            self.window.sync_position()
            self.window.show()
        elif not should and self.window.isVisible():
            self.window.hide()
        self._flush_achievements()   # conquistas que esperaram a tela cheia acabar
        self._announce_update()

    def toggle_visible(self) -> None:
        if self.in_tray:
            self.show_from_tray()
        else:
            self.hide_to_tray()

    def hide_to_tray(self) -> None:
        if self.in_tray:
            return
        if not self.has_tray:
            self.pet.line("sem_bandeja", "reaction")
            return
        self.in_tray = True
        self.pet.line("para_bandeja", "reaction")
        QTimer.singleShot(1300, self.apply_visibility)
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            self.notify(self.settings.name, "Tô aqui na bandeja! Clica no meu ícone pra me trazer de volta.", 5000)
        self.save()

    def show_from_tray(self) -> None:
        if not self.in_tray:
            self.apply_visibility()
            return
        self.in_tray = False
        self.apply_visibility()
        self.pet.line("da_bandeja", "reaction")
        self.save()

    # ---- ações -----------------------------------------------------------
    def on_toolbar(self, bid: str) -> None:
        cats = {"comer": "comidas", "beber": "bebidas", "atividades": "atividades"}
        if bid in cats:
            self._popup = menus.category_menu(self, cats[bid])
            self._popup_beside(self._popup)
        elif bid == "dormir":
            if self.pet.state == "sleep":
                self.pet.wake(forced=True)
            else:
                self.pet.request_sleep()
        elif bid == "carinho":
            self.pet_hug()
        elif bid == "bandeja":
            self.hide_to_tray()
        elif bid == "menu":
            self.show_context_menu()

    def show_context_menu(self) -> None:
        self._popup = QMenu()
        menus.fill_main(self, self._popup)
        self._popup_beside(self._popup)

    def _popup_beside(self, menu: QMenu) -> None:
        """Abre o menu do lado do creeper (e do painel/barra, se estiverem aparecendo), sem cobrir nada."""
        ui = self.window.ui_rect()
        size = menu.sizeHint()
        screen = self.window.screen() or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = ui.right() + 8
        if x + size.width() > geo.right():          # não cabe à direita: abre à esquerda
            x = ui.left() - 8 - size.width()
        x = max(geo.left(), x)
        y = max(geo.top(), min(ui.top(), geo.bottom() - size.height()))
        menu.popup(QPoint(x, y))

    def pet_hug(self) -> None:
        self.pet.stroke()

    # ---- configurações ---------------------------------------------------
    def set_scale(self, scale: int) -> None:
        self.settings.scale = scale
        self.window.resize_for_scale()
        self.save()

    def set_setting(self, key: str, value) -> None:
        setattr(self.settings, key, value)
        if key == "hide_fullscreen" and not value:
            self.fs_hidden = False
            self.apply_visibility()
        if key in ("sound", "sound_volume"):
            self.play_sound("pop")  # amostra do volume escolhido
        if key == "climb":
            self.refresh_platforms()   # desligou: ele desce da janela na hora
        if key == "check_updates":
            if value:
                self.updater.start()
            else:
                self.updater.stop()
        self.save()

    def autostart_enabled(self) -> bool:
        try:
            return desktop.autostart_enabled()
        except Exception:
            return False

    def set_autostart(self, enabled: bool) -> None:
        try:
            desktop.set_autostart(enabled)
        except Exception as exc:
            self.on_say(f"Não consegui mudar o início automático: {exc}", "reaction")

    def rename(self) -> None:
        name, ok = QInputDialog.getText(None, "Renomear", "Novo nome do creeper:", text=self.settings.name)
        name = name.strip()[:24]
        if ok and name:
            self.settings.name = name
            self.pet.line("renomeado")
            self.save()

    # ---- versão nova ----------------------------------------------------
    def on_update_result(self, release: updater.Release | None, error: str, manual: bool) -> None:
        if release:
            self.update_offer = release
        if manual:   # você pediu pra procurar: sempre responde
            if release:
                self.open_update()
            elif error:
                self.tell(self.lines.pick("versao_sem_internet", nome=self.settings.name)
                          or "Não consegui ver se tem versão nova.")
            else:
                self.tell(self.lines.pick("versao_em_dia", nome=self.settings.name, versao=__version__)
                          or f"Já tô na versão mais nova ({__version__}).")
        elif (release and release.version != self.settings.skip_version
              and time.monotonic() >= self._update_snooze_until):
            self._update_announce = True
            self._announce_update()

    def _announce_update(self) -> None:
        """Conta da versão nova: no balão (com botão "Ver") ou num aviso da bandeja."""
        if not self._update_announce or not self.update_offer or self.fs_hidden:
            return   # em tela cheia, espera o jogo/vídeo acabar
        self._update_announce = False
        version = self.update_offer.version
        if self.window.isVisible():
            text = (self.lines.pick("versao_nova", nome=self.settings.name, versao=version)
                    or f"Saiu a versão {version}! Quer ver?")
            self.window.show_bubble(text, action="atualizar")
            self.play_sound("lembrete")
        elif self.settings.notifications:
            self.notify(f"{self.settings.name} tem versão nova",
                        f"Saiu a versão {version}. Clique aqui pra ver o que mudou.", 10000, self.open_update)

    def open_update(self) -> None:
        if not self.update_offer:
            return
        if self.window.sticky and self.window.sticky[1] == "atualizar":
            self.window.clear_sticky()
        if self._update_dialog and self._update_dialog.isVisible():
            self._update_dialog.raise_()
            self._update_dialog.activateWindow()
            return
        self._update_dialog = UpdateDialog(self, self.update_offer)
        self._update_dialog.show()

    def check_update_now(self) -> None:
        self.updater.check(manual=True)

    def skip_update(self, release: updater.Release) -> None:
        self.settings.skip_version = release.version
        self.save()

    def snooze_update(self) -> None:
        # não oferece de novo sozinho por um dia (no menu continua)
        self._update_snooze_until = time.monotonic() + UPDATE_SNOOZE_SECONDS

    def finish_update(self, new_file) -> str:
        """Troca o executável pelo novo e reabre. Dando certo, este fecha; senão devolve o erro."""
        target = updater.target_file()
        try:
            updater.install(new_file, target)
        except OSError as exc:
            updater.cleanup(target)
            return f"não consegui trocar o programa ({exc.strerror or exc})"
        self.save()
        server = self.instance_server
        name = server.serverName() if server else ""
        if server:
            server.close()   # libera a vaga de "uma cópia só" pra versão nova
        try:
            updater.relaunch(target)
        except OSError as exc:
            if server:
                server.listen(name)
            return f"a versão nova já está no lugar, mas não abriu ({exc.strerror or exc}); feche e abra de novo"
        self.quit()
        return ""

    def save(self) -> None:
        try:
            write_save(self.settings, self.pet.to_dict(), {"visible": not self.in_tray})
        except OSError:
            pass

    def quit(self) -> None:
        self.save()
        self.tray.hide()
        self.qapp.quit()
