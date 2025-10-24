# -*- coding: utf-8 -*-
import time
import threading
from pathlib import Path
import ctypes
from ctypes import wintypes

import cv2
import numpy as np
import keyboard
import win32gui
from mss import mss

# =========================
# CONFIG
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
LOOP_SLEEP = 0.02      # 50 FPS
SWITCH_MARGIN = 0.02   # switch plus rapide

# =========================
# ETAT
# =========================
SCREEN_CENTER = None
ACTIVE = False
last_tool = None

# =========================
# Win32 SendInput
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
    time.sleep(0.02)
    send_key(vk, False)

def mouse_left(down: bool):
    mi = MOUSEINPUT(0, 0, 0,
                    MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP,
                    0, None)
    inp = INPUT(type=INPUT_MOUSE, ii=INPUT_union(mi=mi))
    SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

# =========================
# Capture
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

# =========================
# Features & Références
# =========================
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
            refs[cat] = np.mean(hists, axis=0)  # profil moyen par catégorie
    return refs

REFS = load_refs()

# =========================
# Classification simple
# =========================
def classify(frame):
    hist = color_hist_hsv(frame)
    scores = {}
    for cat, ref_hist in REFS.items():
        score = cv2.compareHist(hist, ref_hist, cv2.HISTCMP_CORREL)
        scores[cat] = score
    return scores

# =========================
# Worker
# =========================
def worker():
    global ACTIVE, last_tool
    mouse_left(True)
    while ACTIVE:
        frame = grab_frame()
        scores = classify(frame)

        if scores:
            best_cat = max(scores, key=scores.get)
            best_score = scores[best_cat]
            other_cat = "hache" if best_cat == "pioche" else "pioche"
            margin = best_score - scores[other_cat]

            if last_tool is None or (best_cat != last_tool and margin > SWITCH_MARGIN):
                print(f"[INFO] Outil choisi : {best_cat.upper()} (scores={scores}, marge={margin:.3f})")
                if best_cat == "pioche":
                    press_key(0x31)  # touche "1"
                else:
                    press_key(0x32)  # touche "2"
                last_tool = best_cat

        time.sleep(LOOP_SLEEP)
    mouse_left(False)

def toggle():
    global ACTIVE, last_tool
    if not ACTIVE:
        capture_center()
        ACTIVE = True
        last_tool = None
        threading.Thread(target=worker, daemon=True).start()
        print("Auto-minage ACTIVÉ")
    else:
        ACTIVE = False
        print("Auto-minage DÉSACTIVÉ")

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    print("Appuie sur + pour activer/désactiver l’auto-minage.")
    keyboard.add_hotkey("+", toggle)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        if ACTIVE:
            ACTIVE = False
            mouse_left(False)
