"""Liga tudo: necessidades, comportamento, janela, bandeja, lembretes e salvamento."""
import time
from datetime import datetime

from PySide6.QtCore import QElapsedTimer, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QInputDialog, QMenu, QSystemTrayIcon

from . import desktop
from .config import Settings, load_save, write_save
from .content import load_content
from .needs import Needs
from .pet import Pet
from .progress import Progress
from .sound.player import Sounds
from .ui import menus
from .ui.pet_window import PetWindow
from .ui.toast import Toast
from .ui.tray import Tray

FRAME_MS = 33
CARE_CONFIRM_SECONDS = 10 * 60   # quanto tempo dá pra apertar "Fiz!" depois de um lembrete
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

        self.sounds = Sounds(self.settings, self)
        self.pet.sfx = self.play_sound
        self.pet.sfx_stop = self.sounds.stop
        QTimer.singleShot(500, self.sounds.load)  # o que faltar no cache é gerado em segundo plano

        self.window = PetWindow(self)
        self.toast = Toast()
        self.tray = Tray(self)
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
        for ms, slot in ((FRAME_MS, self.tick), (2000, self.slow_tick), (30000, self.care_tick), (60000, self.save)):
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
        self._adapt_frame_rate()

    def _adapt_frame_rate(self) -> None:
        """30 fps quando ele está se mexendo; bem menos quando está parado."""
        pet, win = self.pet, self.window
        moving = (pet.state in ("walk", "exercise", "hiss", "dragged", "fall", "eat", "drink", "exploded")
                  or pet.jump > 0 or pet.squash > 0 or win.dragging)
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
        self.tray.refresh()

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
                self.tray.showMessage("Conquista feita!", ach["nome"], self.tray.icon(), 6000)

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
                self.tray.showMessage(self.settings.name, text, self.tray.icon(), 7000)

    def greet(self) -> None:
        pet = self.pet
        if self.first_run:
            pet.line("primeira_vez")
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
            self.tray.showMessage(self.settings.name, "Tô aqui na bandeja! Clica no meu ícone pra me trazer de volta.",
                                  self.tray.icon(), 5000)
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
    def on_toolbar(self, bid: str, global_pos: QPoint) -> None:
        cats = {"comer": "comidas", "beber": "bebidas", "atividades": "atividades"}
        if bid in cats:
            self._popup = menus.category_menu(self, cats[bid])
            self._popup.popup(global_pos)
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
            self.show_context_menu(global_pos)

    def show_context_menu(self, global_pos: QPoint) -> None:
        self._popup = QMenu()
        menus.fill_main(self, self._popup)
        self._popup.popup(global_pos)

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

    def save(self) -> None:
        try:
            write_save(self.settings, self.pet.to_dict(), {"visible": not self.in_tray})
        except OSError:
            pass

    def quit(self) -> None:
        self.save()
        self.tray.hide()
        self.qapp.quit()
