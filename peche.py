# -*- coding: utf-8 -*-
import time
import threading
import keyboard
import sounddevice as sd
import numpy as np
import librosa
import win32api, win32con
from collections import deque
import winsound
import sys
from PySide6 import QtCore, QtGui, QtWidgets

# ============================================================
# ⚙️ CONFIG
# ============================================================
DEVICE_INDEX = 17
DURATION = 0.4
SUPPORTED_SAMPLE_RATES = [48000, 44100]

ENERGY_THRESHOLD = 0.00010
BASS_BAND = (230, 800)
PEAK_DELTA_RATIO = 3.5
DECAY_FACTOR = 0.95
DELAY_AFTER_THROW_SEC = 3
COOLDOWN_SEC = 0.35
BACKGROUND_MEMORY = 10  # allongée pour une meilleure stabilité

# Timer (secondes)
ALERT_TIME = 510      # 8:30
STOP_TIME = 585        # 9:45

# ============================================================
# 🧠 ÉTAT GLOBAL
# ============================================================
SR_USED = None
running = False
_last_throw_t = -1e9
_last_trigger_t = 0
recent_background = deque(maxlen=BACKGROUND_MEMORY)

state = {
    "STATUS": "OFF",        # OFF / CALIBRATION / ACTIVE
    "start_time": None,
    "calibration_step": 0,
    "calibration_total": BACKGROUND_MEMORY
}

# ============================================================
# 🖱️ ACTIONS MINECRAFT
# ============================================================
def right_click():
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
    time.sleep(0.03)
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)

# ============================================================
# 🎧 AUDIO
# ============================================================
def try_open_sample_rate():
    for sr in SUPPORTED_SAMPLE_RATES:
        try:
            with sd.InputStream(device=DEVICE_INDEX, samplerate=sr, channels=1, dtype='float32'):
                return sr
        except Exception:
            pass
    raise RuntimeError("Aucun sample rate utilisable.")

def ensure_initialized():
    global SR_USED
    if SR_USED is None:
        SR_USED = try_open_sample_rate()
        print(f"[INFO] SR sélectionné : {SR_USED} Hz")

def capture_once(sr):
    try:
        with sd.InputStream(device=DEVICE_INDEX, samplerate=sr, channels=1, dtype='float32') as stream:
            frames = int(DURATION * sr)
            data, _ = stream.read(frames)
            return data.flatten()
    except Exception as e:
        print(f"[ERROR] capture_once: {e}")
        return None

# ============================================================
# 🎧 CALIBRATION (prise de son)
# ============================================================
def calibration_phase():
    global recent_background
    recent_background.clear()
    state["STATUS"] = "CALIBRATION"
    state["calibration_step"] = 0

    ensure_initialized()

    for i in range(BACKGROUND_MEMORY):
        y = capture_once(SR_USED)
        if y is None:
            continue
        S = np.abs(librosa.stft(y, n_fft=1024, hop_length=256)) ** 2
        freqs = librosa.fft_frequencies(sr=SR_USED, n_fft=1024)
        idx = np.where((freqs >= BASS_BAND[0]) & (freqs <= BASS_BAND[1]))[0]
        bass_energy = np.mean(S[idx, :], axis=0)
        bass_avg = float(np.mean(bass_energy))
        recent_background.append(bass_avg)
        state["calibration_step"] = i + 1
        print(f"[CALIBRATION] Capture {i+1}/{BACKGROUND_MEMORY}")
        time.sleep(0.2)

    print("[INFO] Calibration terminée.")
    state["STATUS"] = "ACTIVE"
    state["start_time"] = time.time()

# ============================================================
# 🔍 DÉTECTION DU PLOUF
# ============================================================
def detect_splash():
    global _last_throw_t, _last_trigger_t, recent_background

    now = time.time()
    since_throw = now - _last_throw_t

    if since_throw < DELAY_AFTER_THROW_SEC:
        time.sleep(0.05)
        return False

    y = capture_once(SR_USED)
    if y is None:
        return False

    total_energy = np.sqrt(np.mean(y**2))
    if total_energy < ENERGY_THRESHOLD:
        return False

    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=256)) ** 2
    freqs = librosa.fft_frequencies(sr=SR_USED, n_fft=1024)
    idx = np.where((freqs >= BASS_BAND[0]) & (freqs <= BASS_BAND[1]))[0]
    bass_energy = np.mean(S[idx, :], axis=0)
    bass_avg = float(np.mean(bass_energy))

    background_mean = np.mean(recent_background)
    recent_background.append(bass_avg)

    ratio = bass_avg / (background_mean + 1e-9)
    delta = bass_avg - background_mean

    RATIO_TRIGGER = PEAK_DELTA_RATIO
    DELTA_TRIGGER = background_mean * 0.025

    if (ratio >= RATIO_TRIGGER and delta >= DELTA_TRIGGER
            and (now - _last_trigger_t) >= COOLDOWN_SEC):
        _last_trigger_t = now
        print(f"[LOG] ratio={ratio:.2f} Δ={delta:.6f} → DETECTED ✅")
        return True
    else:
        return False

# ============================================================
# 🎣 BOUCLE PRINCIPALE
# ============================================================
def sequence():
    global running, _last_throw_t
    calibration_phase()

    while running and state["STATUS"] == "ACTIVE":
        right_click()  # lancer la ligne
        _last_throw_t = time.time()
        detected = False

        while not detected and running and state["STATUS"] == "ACTIVE":
            detected = detect_splash()

        if not running:
            break

        right_click()  # ramène
        time.sleep(1)

def toggle_run():
    global running
    if not running:
        running = True
        threading.Thread(target=sequence, daemon=True).start()
        print("🎣 Pêche automatique en cours (avec calibration).")
    else:
        stop()

def stop():
    global running
    running = False
    state["STATUS"] = "OFF"
    print("⛔ Pêche automatique arrêtée.")

# ============================================================
# ⏱️ OVERLAY
# ============================================================
class Overlay(QtWidgets.QWidget):
    def __init__(self, state_ref):
        super().__init__()
        self.state = state_ref

        screens = QtWidgets.QApplication.screens()
        self.screen = screens[0]
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

        self.green = QtGui.QColor(0, 255, 0)
        self.yellow = QtGui.QColor(255, 200, 0)
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

        self.check_timer = QtCore.QTimer(self)
        self.check_timer.timeout.connect(self.check_time_events)
        self.check_timer.start(1000)
        self.last_beep_time = -1

    def check_time_events(self):
        status = self.state["STATUS"]
        started = self.state["start_time"]
        if status != "ACTIVE" or not started:
            return

        elapsed = int(time.time() - started)
        if elapsed >= STOP_TIME:
            stop()
            winsound.Beep(1000, 200)
            return

        if elapsed >= ALERT_TIME:
            interval = 5
            if elapsed >= STOP_TIME:
                interval = 1
            if elapsed % interval == 0 and elapsed != self.last_beep_time:
                winsound.Beep(800, 150)
                self.last_beep_time = elapsed

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        w, h = self.width(), self.height()
        status = self.state["STATUS"]
        started = self.state["start_time"]

        title = "Pêche automatique"
        timer_text = "00:00"

        if status == "ACTIVE" and started:
            elapsed = int(time.time() - started)
            minutes = elapsed // 60
            seconds = elapsed % 60
            timer_text = f"{minutes:02d}:{seconds:02d}"

        if status == "OFF":
            status_text = "DESACTIVÉ"
            color = self.red
        elif status == "CALIBRATION":
            step = self.state["calibration_step"]
            total = self.state["calibration_total"]
            status_text = f"PRISE DE SON {step}/{total}"
            color = self.yellow
        else:
            status_text = "ACTIF"
            color = self.green

        y = h - self.margin - self.offset_y

        p.setFont(self.font_small)
        fm_small = QtGui.QFontMetrics(self.font_small)
        x = w - self.margin - fm_small.horizontalAdvance(title)
        p.setPen(self.green)
        p.drawText(x, y, title)
        y -= fm_small.height() + self.line_gap

        p.setFont(self.font_big)
        fm_big = QtGui.QFontMetrics(self.font_big)
        x = w - self.margin - fm_big.horizontalAdvance(timer_text)
        p.setPen(self.green)
        p.drawText(x, y - self.timer_offset, timer_text)
        y -= fm_big.height() + self.line_gap

        x = w - self.margin - fm_big.horizontalAdvance(status_text)
        p.setPen(color)
        p.drawText(x, y, status_text)

# ============================================================
# 🏁 MAIN
# ============================================================
def main():
    keyboard.add_hotkey("+", toggle_run)
    for k in ["z", "q", "s", "d"]:
        keyboard.add_hotkey(k, stop)

    print("=== Périphériques audio disponibles ===")
    print(sd.query_devices())
    print(f"[INFO] Capture via device {DEVICE_INDEX} (Mixage stéréo)")
    print("Programme prêt. Appuie sur '+' pour démarrer/arrêter.")

    app = QtWidgets.QApplication(sys.argv)
    overlay = Overlay(state)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
