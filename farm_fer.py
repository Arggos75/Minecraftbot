# -*- coding: utf-8 -*-
"""
Farm Fer - version simplifiée et propre
- Start/stop : '+' key
- Stop d'urgence : Z, Q, S, D
- Overlay : chrono, statut, cooldowns et action en cours
- Séquence : coffre (10s) -> Achat -> Vente -> AFK
- Utilise les vraies flèches directionnelles
"""
import sys
import time
import threading
import ctypes
from ctypes import wintypes
import math
import keyboard
import winsound
from PySide6 import QtCore, QtGui, QtWidgets

# =============================
# CONFIG
# =============================
TITLE = "Farm Fer"
BEEP_START_SECONDS = 510
AUTO_STOP_SECONDS = 585

# Durées (s)
T_OPEN = 2
T_WAIT = 10
T_POST = 2
T_AFK = 60
SHORT_50 = 0.05
SHORT_20 = 0.5
KEYEVENTF_KEYUP       = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_SCANCODE    = 0x0008

MapVirtualKey = ctypes.windll.user32.MapVirtualKeyW


# =============================
# STATE GLOBAL
# =============================
state = {
    "ACTIVE": False,
    "start_time": None,
    "action": "Idle",
    "cooldowns": {},
    "last_beep_time": -1,
}

# =============================
# INPUTS
# =============================
PUL = ctypes.POINTER(ctypes.c_ulong)

class MOUSEINPUT(ctypes.Structure):
    _fields_ = (("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", PUL))

class KEYBDINPUT(ctypes.Structure):
    _fields_ = (("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", PUL))

class INPUT_union(ctypes.Union):
    _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT))

class INPUT(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("ii", INPUT_union))

SendInput = ctypes.windll.user32.SendInput
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP   = 0x0004
KEYEVENTF_KEYUP      = 0x0002

VK_T = 0x54
VK_RETURN = 0x0D
VK_UP = 0x26
VK_DOWN = 0x28

def press_vk_scancode(vk: int, extended: bool = False, hold_s: float = 0.01):
    """Envoie une touche par scancode (robuste aux layouts). extended=True pour les flèches."""
    if not state["ACTIVE"]:
        return
    sc = MapVirtualKey(vk, 0)  # 0 = MAPVK_VK_TO_VSC
    flags_down = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if extended else 0)
    flags_up   = flags_down | KEYEVENTF_KEYUP

    ki_down = KEYBDINPUT(wVk=0, wScan=sc, dwFlags=flags_down, time=0, dwExtraInfo=None)
    SendInput(1, ctypes.byref(INPUT(type=INPUT_KEYBOARD, ii=INPUT_union(ki=ki_down))), ctypes.sizeof(INPUT))

    time.sleep(hold_s)

    ki_up = KEYBDINPUT(wVk=0, wScan=sc, dwFlags=flags_up, time=0, dwExtraInfo=None)
    SendInput(1, ctypes.byref(INPUT(type=INPUT_KEYBOARD, ii=INPUT_union(ki=ki_up))), ctypes.sizeof(INPUT))

    # Important : courte pause entre deux pressions identiques
    time.sleep(0.6)


def press_key(vk, hold=0.01):
    """Envoie une touche en mode 'classique', sauf pour les flèches (extended+scancode)."""
    # Flèches -> scancode + extended (robuste)
    if vk in (0x25, 0x26, 0x27, 0x28):  # LEFT, UP, RIGHT, DOWN
        press_vk_scancode(vk, extended=True, hold_s=hold)
        return

    if not state["ACTIVE"]:
        return
    ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=None)
    SendInput(1, ctypes.byref(INPUT(type=INPUT_KEYBOARD, ii=INPUT_union(ki=ki))), ctypes.sizeof(INPUT))
    time.sleep(hold)
    ki.dwFlags = KEYEVENTF_KEYUP
    SendInput(1, ctypes.byref(INPUT(type=INPUT_KEYBOARD, ii=INPUT_union(ki=ki))), ctypes.sizeof(INPUT))

def mouse_click():
    if not state["ACTIVE"]: return
    mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, None)
    SendInput(1, ctypes.byref(INPUT(type=INPUT_MOUSE, ii=INPUT_union(mi=mi))), ctypes.sizeof(INPUT))
    time.sleep(0.02)
    mi.dwFlags = MOUSEEVENTF_LEFTUP
    SendInput(1, ctypes.byref(INPUT(type=INPUT_MOUSE, ii=INPUT_union(mi=mi))), ctypes.sizeof(INPUT))

# =============================
# OUTILS
# =============================
def update_cooldown(label, remaining):
    if remaining >= 1:
        state["cooldowns"][label] = int(math.ceil(remaining))
    else:
        state["cooldowns"].pop(label, None)

def do_step(label, duration=None, press=None):
    """Exécute une étape : attente (avec cooldown) et/ou appui touche"""
    if not state["ACTIVE"]:
        return False

    state["action"] = label

    # Gestion de la temporisation
    if duration and duration >= 1:
        end = time.perf_counter() + duration
        while state["ACTIVE"] and time.perf_counter() < end:
            update_cooldown(label, end - time.perf_counter())
            time.sleep(0.02)
        state["cooldowns"].pop(label, None)
        if not state["ACTIVE"]:
            return False
    elif duration and duration < 1:
        time.sleep(duration)

    # Gestion des appuis clavier/souris
    if not state["ACTIVE"]:
        return False
    if press:
        if press == "click":
            mouse_click()
        elif isinstance(press, list):
            for p in press:
                if not state["ACTIVE"]: return False
                press_key(p)
                time.sleep(SHORT_20)
        else:
            press_key(press)

    return state["ACTIVE"]

# =============================
# WORKER PRINCIPAL
# =============================
def run_sequence():
    try:
        # Ouverture du coffre
        if not do_step("Ouverture du coffre", duration=T_OPEN, press="click"):
            return

        while state["ACTIVE"]:
            # Ouverture du coffre
            if not do_step("Ouverture du coffre", duration=T_OPEN, press="click"):
                return
            # Achat
            if not do_step("Achat - attente", duration=T_WAIT): break
            if not do_step("Achat - T", press=VK_T): break
            if not do_step("Achat - flèches", press=[VK_UP, VK_UP]): break
            if not do_step("Achat - validation", duration=T_POST): break
            if not do_step("Achat - Entrée", press=VK_RETURN): break

            # Vente
            if not do_step("Vente - attente", duration=T_WAIT): break
            if not do_step("Vente - T", press=VK_T): break
            if not do_step("Vente - flèches", press=[VK_UP, VK_UP]): break
            if not do_step("Vente - validation", duration=T_POST): break
            if not do_step("Vente - Entrée", press=VK_RETURN): break

            # AFK
            if not do_step("AFK", duration=T_AFK): break

    finally:
        state["action"] = "Idle"
        state["cooldowns"].clear()

# =============================
# TOGGLE / STOP
# =============================
def toggle():
    if not state["ACTIVE"]:
        state["ACTIVE"] = True
        state["start_time"] = time.time()
        threading.Thread(target=run_sequence, daemon=True).start()
        print("[Farm Fer] ACTIVÉ")
    else:
        state["ACTIVE"] = False
        print("[Farm Fer] DÉSACTIVÉ")

def stop():
    state["ACTIVE"] = False
    print("[Farm Fer] ARRÊT FORCÉ")

# =============================
# OVERLAY
# =============================
class Overlay(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setGeometry(QtWidgets.QApplication.primaryScreen().geometry())

        self.font_small = QtGui.QFont("Consolas", 16, QtGui.QFont.Bold)
        self.font_big = QtGui.QFont("Consolas", 40, QtGui.QFont.Black)
        self.green, self.red = QtGui.QColor(0, 220, 0), QtGui.QColor(220, 0, 0)

        QtCore.QTimer.singleShot(0, self.show)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(33)
        self.check_timer = QtCore.QTimer()
        self.check_timer.timeout.connect(self.check_time)
        self.check_timer.start(1000)

    def check_time(self):
        if not state["ACTIVE"] or not state["start_time"]: return
        elapsed = int(time.time() - state["start_time"])
        if elapsed >= AUTO_STOP_SECONDS:
            state["ACTIVE"] = False
            winsound.Beep(1000, 200)
        elif elapsed >= BEEP_START_SECONDS:
            if elapsed % 5 == 0 and elapsed != state["last_beep_time"]:
                winsound.Beep(800, 150)
                state["last_beep_time"] = elapsed

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        w, h = self.width(), self.height()
        y = h - 60
        active = state["ACTIVE"]
        elapsed = int(time.time() - state["start_time"]) if active and state["start_time"] else 0
        timer = f"{elapsed//60:02d}:{elapsed%60:02d}"
        pen = self.green if active else self.red

        # Draw elements
        def draw(text, font, color=None):
            nonlocal y
            p.setFont(font)
            p.setPen(color or self.green)
            fm = QtGui.QFontMetrics(font)
            x = w - 20 - fm.horizontalAdvance(text)
            p.drawText(QtCore.QPoint(int(x), int(y)), text)
            y -= fm.height() + 6

        draw(TITLE, self.font_small)
        draw(timer, self.font_big)
        draw("ACTIVER" if active else "DESACTIVER", self.font_big, pen)
        for lbl, val in sorted(state["cooldowns"].items(), key=lambda kv: -kv[1]):
            draw(f"{lbl}: {val}s", self.font_small)
        draw(f"Action: {state['action']}", self.font_small)

# =============================
# MAIN
# =============================
def main():
    keyboard.add_hotkey("+", toggle)
    for k in ["z", "q", "s", "d"]:
        keyboard.add_hotkey(k, stop)
    app = QtWidgets.QApplication(sys.argv)
    Overlay()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
