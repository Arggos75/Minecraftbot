import time
import threading
import keyboard
import sounddevice as sd
import numpy as np
import librosa
import win32api, win32con
from collections import deque

# ============================================================
# ⚙️ CONFIG
# ============================================================
DEVICE_INDEX = 17
DURATION = 0.4              # petite fenêtre pour réactivité
SUPPORTED_SAMPLE_RATES = [48000, 44100]

# ============================================================
# 🎧 DÉTECTION ADAPTATIVE (ajustée sur tes logs)
# ============================================================
ENERGY_THRESHOLD = 0.00010
BASS_BAND = (230, 800)
PEAK_DELTA_RATIO = 3.5       # ratio bon, tes ploufs sont à 11–14
DECAY_FACTOR = 0.95          # ↑ accepte les ploufs longs (avant c’était 0.6)
DELAY_AFTER_THROW_SEC = 1.2
COOLDOWN_SEC = 0.35
BACKGROUND_MEMORY = 6
DELAY_AFTER_THROW_SEC = 3  # (0.8 à 1.2 selon ton volume de canne)


# ============================================================
# ÉTAT GLOBAL
# ============================================================
SR_USED = None
running = False
_last_throw_t = -1e9
_last_trigger_t = 0
recent_background = deque(maxlen=BACKGROUND_MEMORY)

# ============================================================
# 🖱️ ACTIONS MINECRAFT
# ============================================================
def right_click():
    """Simule un clic droit (lancer/ramener)."""
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
    time.sleep(0.03)
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)

# ============================================================
# 🎵 AUDIO
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
# 🔍 DÉTECTION ADAPTATIVE DU PLOUF
# ============================================================
def detect_splash():
    global _last_throw_t, _last_trigger_t, recent_background

    now = time.time()
    since_throw = now - _last_throw_t

    # 🧱 1. Blindage : ignorer tout son pendant la phase de lancer
    if since_throw < DELAY_AFTER_THROW_SEC:
        time.sleep(0.05)
        return False

    # 2. Capture audio
    y = capture_once(SR_USED)
    if y is None:
        return False

    total_energy = np.sqrt(np.mean(y**2))
    if total_energy < ENERGY_THRESHOLD:
        return False

    # 3. Analyse basse fréquence
    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=256)) ** 2
    freqs = librosa.fft_frequencies(sr=SR_USED, n_fft=1024)
    idx = np.where((freqs >= BASS_BAND[0]) & (freqs <= BASS_BAND[1]))[0]
    bass_energy = np.mean(S[idx, :], axis=0)
    bass_avg = float(np.mean(bass_energy))

    # 4. Apprentissage du fond (uniquement hors phase de lancer)
    if len(recent_background) < BACKGROUND_MEMORY:
        recent_background.append(bass_avg)
        return False

    background_mean = np.mean(recent_background)
    recent_background.append(bass_avg)

    # 5. Détection par contraste (avec seuil double : ratio + delta)
    ratio = bass_avg / (background_mean + 1e-9)
    delta = bass_avg - background_mean

    # 💬 seuils : ratio pour la forme, delta pour l'amplitude absolue
    RATIO_TRIGGER = PEAK_DELTA_RATIO  # ex: 3.5
    DELTA_TRIGGER = background_mean * 0.025  # 2.5% au-dessus du fond → vrai plouf ~>0.02

    if (ratio >= RATIO_TRIGGER and delta >= DELTA_TRIGGER
            and (now - _last_trigger_t) >= COOLDOWN_SEC):
        _last_trigger_t = now
        print(f"[LOG] ratio={ratio:.2f} Δ={delta:.6f} seuilΔ={DELTA_TRIGGER:.6f} "
              f"fond={background_mean:.6f} → DETECTED ✅ (action immédiate)")
        return True
    else:
        print(f"[LOG] ratio={ratio:.2f} Δ={delta:.6f} seuilΔ={DELTA_TRIGGER:.6f} "
              f"fond={background_mean:.6f} → rejeté")
        return False


# ============================================================
# 🎣 BOUCLE PRINCIPALE
# ============================================================
def sequence():
    global running, _last_throw_t
    ensure_initialized()

    while running:
        right_click()
        _last_throw_t = time.time()
        detected = False

        while not detected and running:
            detected = detect_splash()

        if not running:
            break


        right_click()
        time.sleep(1)

def toggle_run():
    global running
    if not running:
        running = True
        threading.Thread(target=sequence, daemon=True).start()
        print("🎣 Pêche automatique activée (mode adaptatif).")
    else:
        running = False
        print("⛔ Pêche automatique arrêtée.")

def stop():
    global running
    running = False
    print("⛔ Arrêt forcé.")

# ============================================================
# ⌨️ RACCORCIS CLAVIER
# ============================================================
keyboard.add_hotkey("+", toggle_run)
keyboard.add_hotkey("q", stop)
keyboard.add_hotkey("s", stop)
keyboard.add_hotkey("d", stop)
keyboard.add_hotkey("z", stop)

print("=== Périphériques audio disponibles ===")
print(sd.query_devices())
print(f"[INFO] Capture via device {DEVICE_INDEX} (Mixage stéréo)")
print("Programme prêt. Appuie sur '+' pour démarrer/arrêter.")
keyboard.wait()
