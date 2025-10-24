import sys
import time
import threading
import keyboard
import win32gui, win32con, win32api
import winsound
from PySide6 import QtCore, QtGui, QtWidgets
import random

# 37 48
NB_BLOC = 48

VK_F3 = 0x72
VK_C  = 0x43
VK_Q  = 0x51  # gauche
VK_S  = 0x53  # arrière
VK_D  = 0x44  # droite
VK_Z  = 0x5A  # avant
VK_E  = 0x45  # touche E
VK_T = 0x54  # touche T
VK_SLASH = 0xBF   # touche / (slash, même touche que le ? sur un clavier FR)
VK_S = 0x53
VK_E = 0x45
VK_L = 0x4C
VK_A = 0x41
VK_SPACE = 0x20
VK_ESCAPE = 0x1B

state = {
    "ACTIVE": False,
    "start_time": None,
    "current_tool": "?",
    "current_scores": {"pioche": 0.0, "hache": 0.0}
}

Chest = {
    1: (1064, 536),
    2: (1124, 538),
    3: (1179, 530),
    4: (1239, 545),
    5: (1283, 544),
    6: (1340, 540),
    7: (1396, 548),
    8: (1446, 525),
    9: (1504, 555),
}

# --- Déplacements (ZQSD) ---
COEFF_VITESSE = 0.55
TIME_PER_BLOCK = (4.0 / 19.0) * COEFF_VITESSE
SLOW_FACTOR = 2.0
LOOP_SLEEP = 0.02

# --- État global ---
_running_lock = threading.Lock()
_running = False
_stop_event = threading.Event()
_seq_thread = None
_simulated_keys_active = set()  # {'q','s','d','z'}

# =========================
# ==== ARRÊT & TOUCHES ====
# =========================

def release_all_keys_and_mouse():
    """Relâche toutes les touches et clics éventuellement coincés."""
    for vk in (VK_Z, VK_Q, VK_S, VK_D, VK_E, win32con.VK_SHIFT,
               win32con.VK_CONTROL, win32con.VK_MENU):
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)


def _any_stop_key_pressed() -> bool:
    """Vrai si l'utilisateur presse Z/Q/S/D (hors touches simulées)."""
    for key in ('q', 's', 'd', 'z'):
        if key in _simulated_keys_active:
            continue
        try:
            if keyboard.is_pressed(key):
                return True
        except:
            pass
    return False


def _should_stop() -> bool:
    """Renvoie True si un arrêt est demandé (événement ou touche)."""
    if _stop_event.is_set():
        return True
    if _any_stop_key_pressed():
        request_stop("Touche Z/Q/S/D pressée")
        return True
    return False


def request_stop(reason: str = ""):
    """Déclenche l'arrêt global et relâche toutes les touches."""
    global _running
    if not _stop_event.is_set():
        _stop_event.set()
        try:
            arret_plantee()
            release_all_keys_and_mouse()
        except Exception:
            pass
        print("Séquence: arrêt demandé" + (f" ({reason})" if reason else ""))
    with _running_lock:
        _running = False


def _press_key(vk_code: int, duration: float):
    """Appuie sur une touche pendant une durée, interrompable immédiatement."""
    win32api.keybd_event(vk_code, 0, 0, 0)
    start = time.time()
    try:
        while time.time() - start < duration:
            if _should_stop():
                return
            time.sleep(0.02)
    finally:
        win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)

# =========================
# ==== ACTIONS CLAVIER ====
# =========================

def click_left():
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.02)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

def click_right():
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
    time.sleep(0.02)
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)

def press_shift_down():
    win32api.keybd_event(win32con.VK_SHIFT, 0, 0, 0)

def release_shift():
    win32api.keybd_event(win32con.VK_SHIFT, 0, win32con.KEYEVENTF_KEYUP, 0)

def _duration_for_blocks(nb_blocs: float) -> float:
    base = nb_blocs * TIME_PER_BLOCK
    return base * SLOW_FACTOR

def ouvrir_inventaire():
    print("[Inventory] Ouverture de l’inventaire (touche E)")
    _press_key(VK_E, 0.1)
    time.sleep(0.2)

def deplacement_gauche(nb_blocs: float):
    duration = _duration_for_blocks(nb_blocs)
    print(f"[Move] ← Gauche {nb_blocs} blocs ({duration:.2f}s)")
    _press_key(VK_Q, duration)

def deplacement_droite(nb_blocs: float):
    duration = _duration_for_blocks(nb_blocs)
    print(f"[Move] → Droite {nb_blocs} blocs ({duration:.2f}s)")
    _press_key(VK_D, duration)

def deplacement_avant(nb_blocs: float):
    duration = _duration_for_blocks(nb_blocs)
    print(f"[Move] ↑ Avant {nb_blocs} blocs ({duration:.2f}s)")
    _press_key(VK_Z, duration)

def deplacement_arriere(nb_blocs: float):
    duration = _duration_for_blocks(nb_blocs)
    print(f"[Move] ↓ Arrière {nb_blocs} blocs ({duration:.2f}s)")
    _press_key(VK_S, duration)

def plantee():
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
    print("[Farm] Clic gauche maintenu (plantée).")

def arret_plantee():
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
    print("[Farm] Clic gauche relâché (arrêt plantée).")

def changement_graine(slot_num: int):
    vk_code = 0x30 + slot_num if slot_num != 0 else 0x30
    print(f"[Hotbar] Sélection du slot {slot_num}")
    _press_key(vk_code, 0.05)

# =========================
# ===== OVERLAY UI ========
# =========================

def pick_other_screen_index() -> int:
    screens = QtWidgets.QApplication.screens()
    if not screens:
        return 0
    primary = QtGui.QGuiApplication.primaryScreen()
    for i, s in enumerate(screens):
        if s != primary:
            return i
    return 0

class Overlay(QtWidgets.QWidget):
    def __init__(self, state_ref, screen_index=None):
        super().__init__()
        self.state = state_ref

        screens = QtWidgets.QApplication.screens()
        if screen_index is None:
            screen_index = pick_other_screen_index()
        if screen_index >= len(screens):
            screen_index = 0
        self.screen = screens[screen_index]
        geo = self.screen.geometry()

        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.Tool |
            QtCore.Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setGeometry(geo)
        self.show()
        if self.windowHandle() is not None:
            self.windowHandle().setScreen(self.screen)
        self.setGeometry(geo)

        self.green = QtGui.QColor(0, 255, 0)
        self.red = QtGui.QColor(255, 0, 0)
        self.font_small = QtGui.QFont("Consolas", 16, QtGui.QFont.Bold)
        self.font_big = QtGui.QFont("Consolas", 40, QtGui.QFont.Black)

        self.margin = 20
        self.line_gap = 6
        self.offset_y = 40
        self.timer_offset = 0

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(33)

        self.check_timer = QtCore.QTimer(self)
        self.check_timer.timeout.connect(self.check_time_events)
        self.check_timer.start(1000)
        self.last_beep_time = -1

    def check_time_events(self):
        active = self.state["ACTIVE"]
        started = self.state["start_time"]
        if not active or not started:
            return

        elapsed = int(time.time() - started)
        if elapsed >= 585:
            self.state["ACTIVE"] = False
            winsound.Beep(1000, 200)
            return

        if elapsed >= 510:
            interval = 5
            if elapsed >= 585:
                interval = 1
            if elapsed % interval == 0 and elapsed != self.last_beep_time:
                winsound.Beep(800, 150)
                self.last_beep_time = elapsed

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()
        tool = self.state["current_tool"]
        active = self.state["ACTIVE"]
        started = self.state["start_time"]

        generator_text = "Ultimate Farmer bot"
        if active and started:
            elapsed = int(time.time() - started)
            minutes = elapsed // 60
            seconds = elapsed % 60
            timer_text = f"{minutes:02d}:{seconds:02d}"
        else:
            timer_text = "00:00"

        status_text = "ACTIVER" if active else "DESACTIVER"
        y = h - self.margin - self.offset_y

        p.setFont(self.font_small)
        fm_small = QtGui.QFontMetrics(self.font_small)
        x = w - self.margin - fm_small.horizontalAdvance(generator_text)
        p.setPen(self.green)
        p.drawText(x, y, generator_text)
        y -= fm_small.height() + self.line_gap

        p.setFont(self.font_big)
        fm_big = QtGui.QFontMetrics(self.font_big)
        x = w - self.margin - fm_big.horizontalAdvance(timer_text)
        p.setPen(self.green)
        p.drawText(x, y - self.timer_offset, timer_text)
        y -= fm_big.height() + self.line_gap

        status_color = self.red if active else self.green
        x = w - self.margin - fm_big.horizontalAdvance(status_text)
        p.setPen(status_color)
        p.drawText(x, y, status_text)

# =========================
# ==== INVENTAIRE / CHEST =
# =========================

def move_cursor_to(x_target: int, y_target: int, duration: float = 0.25):
    x_start, y_start = win32api.GetCursorPos()
    steps = int(max(5, duration / 0.005))
    for i in range(steps + 1):
        t = i / steps
        t_smooth = t * t * (3 - 2 * t)
        x = int(x_start + (x_target - x_start) * t_smooth)
        y = int(y_start + (y_target - y_start) * t_smooth)
        win32api.SetCursorPos((x, y))
        time.sleep(duration / steps)

def getFromChest(slot_num: int):
    x, y = Chest[slot_num]
    print(f"[Inventory] Slot {slot_num} → position ({x}, {y})")
    move_cursor_to(x, y, duration=0.15)
    press_shift_down()
    click_left()
    release_shift()

def sellAll():
    time.sleep(3)
    _press_key(VK_E, 0.1) # fermer coffre
    time.sleep(1.5)
    _press_key(VK_T, 0.1) # ouvrir chat
    time.sleep(1.5)
    command_sell_all() # comande sell all
    _press_key(VK_ESCAPE, 0.1)  # fermer chat


import random

def command_sell_all():
    """Tape '/sell all' sur un clavier AZERTY FR (Shift + touche 0xBF)."""
    time.sleep(0.3)

    # Slash → Shift + 0xBF
    win32api.keybd_event(win32con.VK_SHIFT, 0, 0, 0)
    win32api.keybd_event(0xBF, 0, 0, 0)
    time.sleep(0.05)
    win32api.keybd_event(0xBF, 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_SHIFT, 0, win32con.KEYEVENTF_KEYUP, 0)

    # Texte : sell all
    sequence = [0x53, 0x45, 0x4C, 0x4C, 0x20, 0x41, 0x4C, 0x4C]
    for vk in sequence:
        win32api.keybd_event(vk, 0, 0, 0)
        time.sleep(random.uniform(0.04, 0.1))
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(random.uniform(0.02, 0.06))

    # Entrée pour valider
    time.sleep(1)
    win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
    win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)

    print("[Chat] Commande '/sell all' envoyée (AZERTY FR, 0xBF).")


def openChest():
    print(f"[Inventory] Open chest")
    click_right()
    time.sleep(0.4)

def closeChest():
    print(f"[Inventory] Close chest")
    time.sleep(0.1)
    _press_key(VK_E, 0.1)
    time.sleep(0.4)

def force_stop():
    state["ACTIVE"] = False
    end_program_check()
    print("Farmer DÉSACTIVÉ (ZQSD)")

def disable_caplock():
    if win32api.GetKeyState(win32con.VK_CAPITAL):
        # Si activé → simule un appui pour le désactiver
        win32api.keybd_event(win32con.VK_CAPITAL, 0, 0, 0)
        win32api.keybd_event(win32con.VK_CAPITAL, 0, win32con.KEYEVENTF_KEYUP, 0)

def refill_inventory():
    openChest()
    getFromChest(1)
    getFromChest(2)
    getFromChest(3)
    getFromChest(4)
    getFromChest(5)
    getFromChest(6)
    getFromChest(7)
    getFromChest(8)
    getFromChest(9)
    closeChest()

def chargement_inventaire():

    disable_caplock()

    #ee/sell all/sell all
    # esrefill_inventory()

    deplacement_arriere(1) #pour pas rouvrir le coffre

    plantee()

    changement_graine(1)
    deplacement_arriere(NB_BLOC)
    deplacement_droite(1)

    changement_graine(2)
    deplacement_avant(NB_BLOC)
    deplacement_droite(1)

    changement_graine(3)
    deplacement_arriere(NB_BLOC)
    deplacement_droite(1)

    changement_graine(4)
    deplacement_avant(NB_BLOC)
    deplacement_droite(1)

    changement_graine(5)
    deplacement_arriere(NB_BLOC)
    deplacement_droite(1)

    changement_graine(6)
    deplacement_avant(NB_BLOC)
    deplacement_droite(1)

    changement_graine(7)
    deplacement_arriere(NB_BLOC)
    deplacement_droite(1)

    changement_graine(8)
    deplacement_avant(NB_BLOC+8)

    arret_plantee()

    sellAll()


    refill_inventory()

    deplacement_arriere(1) #pour pas rouvrir le coffre

    plantee()

    changement_graine(1)
    deplacement_arriere(NB_BLOC)
    deplacement_gauche(1)

    changement_graine(2)
    deplacement_avant(NB_BLOC)
    deplacement_gauche(1)

    changement_graine(3)
    deplacement_arriere(NB_BLOC)
    deplacement_gauche(1)

    changement_graine(4)
    deplacement_avant(NB_BLOC)
    deplacement_gauche(1)

    changement_graine(5)
    deplacement_arriere(NB_BLOC)
    deplacement_gauche(1)

    changement_graine(6)
    deplacement_avant(NB_BLOC)
    deplacement_gauche(1)

    changement_graine(7)
    deplacement_arriere(NB_BLOC)
    deplacement_gauche(1)

    changement_graine(8)
    deplacement_avant(NB_BLOC+8)

    arret_plantee()




# =========================
# ====== SÉQUENCE =========
# =========================

def _sequence():
    print("Séquence démarrée.")
    try:
        chargement_inventaire()
        print("Séquence terminée.")
    finally:
        if _stop_event.is_set():
            print("Séquence interrompue.")
        global _running
        with _running_lock:
            _running = False

# =========================
# ======== FIN ============
# =========================

def end_program_check():
    mouse_left = win32api.GetKeyState(win32con.VK_LBUTTON) < 0
    mouse_right = win32api.GetKeyState(win32con.VK_RBUTTON) < 0
    mouse_middle = win32api.GetKeyState(win32con.VK_MBUTTON) < 0

    keys_to_check = list(range(0x30, 0x5A)) + [
        win32con.VK_SPACE, win32con.VK_SHIFT, win32con.VK_CONTROL,
        win32con.VK_MENU, win32con.VK_LEFT, win32con.VK_RIGHT,
        win32con.VK_UP, win32con.VK_DOWN
    ]
    any_key_pressed = any(win32api.GetAsyncKeyState(k) & 0x8000 for k in keys_to_check)

    if not any_key_pressed and not (mouse_left or mouse_right or mouse_middle):
        for _ in range(3):
            winsound.Beep(1000, 100)
            time.sleep(0.1)
        print("[Fin]")
    else:
        print("[Fin]")

# =========================
# ======== MAIN ===========
# =========================

def _on_plus():
    global _running, _seq_thread
    with _running_lock:
        if not _running:
            _stop_event.clear()
            print("Appui '+' → lancement de la séquence.")
            _running = True
            _seq_thread = threading.Thread(target=_sequence, daemon=True)
            _seq_thread.start()
        else:
            print("Appui '+' → arrêt de la séquence en cours.")
            request_stop("Touche '+' pressée")

def main():
    print("Prêt. '+' pour lancer/arrêter la séquence. Q/S/D/Z → arrêt immédiat pendant la séquence.")
    keyboard.add_hotkey('+', _on_plus)
    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        request_stop("CTRL+C")
        print("Sortie.")

if __name__ == "__main__":
    main()
