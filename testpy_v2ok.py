# -*- coding: utf-8 -*-
import sys
import time
import threading
from pathlib import Path
import ctypes
from ctypes import wintypes

import cv2
import numpy as np
import keyboard
import win32gui, win32con, win32api
from mss import mss
import winsound

from PySide6 import QtCore, QtGui, QtWidgets

# =========================
# CONFIG DÉTECTION
# =========================
REF_IMAGES = {
    "pioche": ["granite.png", "coal_ore.png", "stone.png", "dirt.png"],
    "hache": [
        "bamboo_block_top.png", "spruce_log_top.png", "oak_log_top.png",
        "bamboo_block.png", "spruce_log.png", "oak_log.png"
    ],
}
REF_DIR = Path(".")

BLOCK_SIZE = 64
LOOP_SLEEP = 0.02
SWITCH_MARGIN = 0.02

# =========================
# ÉTAT GLOBAL
# =========================
SCREEN_CENTER = None
state = {
    "ACTIVE": False,
    "start_time": None,
    "current_tool": "?",
    "current_scores": {"pioche": 0.0, "hache": 0.0}
}
last_tool = None

# =========================
# ENVOI D'INPUTS
# =========================
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

def send_key(vk: int, down: bool):
    ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=(0 if down else KEYEVENTF_KEYUP),
                    time=0, dwExtraInfo=None)
    inp = INPUT(type=INPUT_KEYBOARD, ii=INPUT_union(ki=ki))
    SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

def press_key(vk: int):
    send_key(vk, True)
    time.sleep(0.01)
    send_key(vk, False)

def mouse_left(down: bool):
    mi = MOUSEINPUT(0, 0, 0,
                    MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP,
                    0, None)
    inp = INPUT(type=INPUT_MOUSE, ii=INPUT_union(mi=mi))
    SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

# =========================
# CAPTURE & RÉFÉRENCES
# =========================
def capture_center():
    global SCREEN_CENTER
    hwnd = win32gui.GetForegroundWindow()
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    w, h = (r - l), (b - t)
    SCREEN_CENTER = (l + w // 2, t + h // 2)

def grab_frame():
    x, y = SCREEN_CENTER
    region = {"top": y - BLOCK_SIZE//2, "left": x - BLOCK_SIZE//2,
              "width": BLOCK_SIZE, "height": BLOCK_SIZE}
    with mss() as sct:
        frame = np.array(sct.grab(region))[:, :, :3]
    return cv2.resize(frame, (BLOCK_SIZE, BLOCK_SIZE))

def color_hist_hsv(img_bgr):
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0,1,2], None, (8,8,8), [0,180,0,256,0,256])
    hist = cv2.normalize(hist, hist).flatten()
    return hist

def load_refs():
    refs = {}
    for cat, rels in REF_IMAGES.items():
        hists = []
        for rel in rels:
            p = (REF_DIR / rel).resolve()
            img = cv2.imread(str(p))
            if img is None:
                print(f"[ERREUR] Impossible de charger {p}")
                continue
            img = cv2.resize(img, (BLOCK_SIZE, BLOCK_SIZE))
            hists.append(color_hist_hsv(img))
        if hists:
            refs[cat] = np.mean(hists, axis=0)
    return refs

REFS = load_refs()

def classify(frame):
    hist = color_hist_hsv(frame)
    scores = {}
    for cat, ref_hist in REFS.items():
        scores[cat] = cv2.compareHist(hist, ref_hist, cv2.HISTCMP_CORREL)
    return scores

# =========================
# WORKER DÉTECTION
# =========================
def detection_worker():
    global last_tool
    mouse_left(True)
    while state["ACTIVE"]:
        frame = grab_frame()
        scores = classify(frame)
        if scores:
            best_cat = max(scores, key=scores.get)
            other_cat = "hache" if best_cat == "pioche" else "pioche"
            margin = scores[best_cat] - scores.get(other_cat, 0.0)

            state["current_scores"] = {
                "pioche": float(scores.get("pioche", 0.0)),
                "hache": float(scores.get("hache", 0.0))
            }
            state["current_tool"] = best_cat

            if last_tool is None or (best_cat != last_tool and margin > SWITCH_MARGIN):
                if best_cat == "pioche":
                    press_key(0x31)  # touche '1'
                else:
                    press_key(0x32)  # touche '2'
                last_tool = best_cat

        time.sleep(LOOP_SLEEP)
    mouse_left(False)

def toggle_bot():
    global last_tool
    if not state["ACTIVE"]:
        capture_center()
        state["ACTIVE"] = True
        state["start_time"] = time.time()
        last_tool = None
        threading.Thread(target=detection_worker, daemon=True).start()
        print("Auto-minage ACTIVÉ")
    else:
        state["ACTIVE"] = False
        print("Auto-minage DÉSACTIVÉ")

def force_stop():
    state["ACTIVE"] = False
    print("Auto-minage DÉSACTIVÉ (ZQSD)")

# =========================
# OVERLAY PYSIDE6
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
        self.timer_offset = 15

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(33)

        # Timer pour bip et auto-stop
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

        # Auto-stop à 9:45 = 585 s
        if elapsed >= 585:
            self.state["ACTIVE"] = False
            winsound.Beep(1000, 200)
            return

        # Bips après 8:30 = 510 s
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
        scores = self.state["current_scores"]
        active = self.state["ACTIVE"]
        started = self.state["start_time"]

        generator_text = "Generateur bot"
        if active and started:
            elapsed = int(time.time() - started)
            minutes = elapsed // 60
            seconds = elapsed % 60
            timer_text = f"{minutes:02d}:{seconds:02d}"
        else:
            timer_text = "00:00"

        status_text = "ACTIVER" if active else "DESACTIVER"
        tool_text = f"Outil: {tool.upper()} | Pioche: {scores['pioche']:.2f} | Hache: {scores['hache']:.2f}"

        y = h - self.margin - self.offset_y

        # Générateur bot
        p.setFont(self.font_small)
        fm_small = QtGui.QFontMetrics(self.font_small)
        x = w - self.margin - fm_small.horizontalAdvance(generator_text)
        p.setPen(self.green)
        p.drawText(x, y, generator_text)
        y -= fm_small.height() + self.line_gap

        # Timer (remonté de 15 px supplémentaires)
        p.setFont(self.font_big)
        fm_big = QtGui.QFontMetrics(self.font_big)
        x = w - self.margin - fm_big.horizontalAdvance(timer_text)
        p.setPen(self.green)
        p.drawText(x, y - self.timer_offset, timer_text)
        y -= fm_big.height() + self.line_gap

        # Status
        status_color = self.red if active else self.green
        x = w - self.margin - fm_big.horizontalAdvance(status_text)
        p.setPen(status_color)
        p.drawText(x, y, status_text)
        y -= fm_big.height() + self.line_gap

        # Tool + scores
        p.setFont(self.font_small)
        fm_small = QtGui.QFontMetrics(self.font_small)
        x = w - self.margin - fm_small.horizontalAdvance(tool_text)
        p.setPen(self.green)
        p.drawText(x, y, tool_text)

# =========================
# MAIN
# =========================
def main():
    keyboard.add_hotkey("+", toggle_bot)
    for k in ["z","q","s","d"]:
        keyboard.add_hotkey(k, force_stop)

    app = QtWidgets.QApplication(sys.argv)
    overlay = Overlay(state, screen_index=None)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
