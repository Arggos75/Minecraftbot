"""
Minecraft Java Bot (alignement X autour d’une position cible)

Commande copiée : "/execute ... tp @s X Y Z YAW PITCH"

- POSX = X → 🔴 rouge
- POSY = Y → 🟢 vert (hauteur)
- POSZ = Z → 🔵 bleu
(Y = hauteur)

Objectif :
- maintenir X ≈ 41008.5 ± 0.4
- corriger automatiquement Q/D selon YAW
- durée d’appui = |écart| × STEP_GAIN
"""

import time, threading, keyboard, win32api, win32con, pyperclip, re
from statistics import mean

# =========================
# ======= CONFIG ==========
# =========================
VK_Z, VK_S, VK_Q, VK_D, VK_F3, VK_C = 0x5A, 0x53, 0x51, 0x44, 0x72, 0x43
STOP_KEYS = {'q','s','d','z','e','t'}

# --- Cible & marge ---
X_TARGET = 41008.5
X_TOLERANCE = 0.4            # ±0.4 autour de la cible
F3C_INTERVAL = 2.0           # F3+C toutes les 2 s

# --- Réglage du pas ---
STEP_GAIN = 0.020            # <<< facteur à ajuster (durée = |écart| × STEP_GAIN)
MIN_STEP = 0.00
MAX_STEP = 0.15

SMOOTH_N = 3                 # moyenne mobile sur 3 valeurs

_running = False
_stop_event = threading.Event()
_thread = None
_x_history = []

EXEC_RE = re.compile(
    r"/execute\s+.*?\s+tp\s+@s\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)",
    re.IGNORECASE
)

# =========================
# ======= UTILS ===========
# =========================
def log(msg): print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def press_key(vk, duration):
    if duration <= 0: return
    win32api.keybd_event(vk, 0, 0, 0)
    time.sleep(duration)
    win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)

def hold_key(vk):    win32api.keybd_event(vk, 0, 0, 0)
def release_key(vk): win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)

# =========================
# ====== F3 + C ===========
# =========================
def f3c_copy():
    """F3+C → lit X et YAW"""
    win32api.keybd_event(VK_F3,0,0,0)
    win32api.keybd_event(VK_C,0,0,0)
    time.sleep(0.05)
    win32api.keybd_event(VK_C,0,win32con.KEYEVENTF_KEYUP,0)
    win32api.keybd_event(VK_F3,0,win32con.KEYEVENTF_KEYUP,0)
    time.sleep(0.1)
    try:
        data = pyperclip.paste()
        m = EXEC_RE.search(data)
        if not m:
            log("Aucune coordonnée trouvée.")
            return None, None
        POSX, _, _, YAW, _ = map(float, m.groups())
        log(f"F3+C → X={POSX:.2f} | YAW={YAW:.1f}°")
        return POSX, YAW
    except Exception as e:
        log(f"Erreur clipboard: {e}")
        return None, None

def yaw_sector(yaw):
    """Renvoie le secteur cardinal (±45° de tolérance)"""
    yaw = (yaw + 360) % 360
    if 315 <= yaw or yaw < 45:   return "S"
    if 45 <= yaw < 135:          return "O"
    if 135 <= yaw < 225:         return "N"
    if 225 <= yaw < 315:         return "E"

def key_for_target_deltaX(delta_sign, sector):
    """
    delta_sign = +1 → on veut augmenter X
    delta_sign = -1 → on veut diminuer X
    """
    if sector == "S":   # face Sud : Q → +X, D → -X
        return VK_Q if delta_sign > 0 else VK_D
    if sector == "N":   # face Nord : D → +X, Q → -X
        return VK_D if delta_sign > 0 else VK_Q
    if sector == "E":   # face Est  : approximation latérale
        return VK_D if delta_sign > 0 else VK_Q
    if sector == "O":   # face Ouest : idem
        return VK_Q if delta_sign > 0 else VK_D
    return None

# =========================
# ======= THREAD ==========
# =========================
def run_sequence():
    global _x_history
    log("Démarrage (Z maintenu)")
    hold_key(VK_Z)
    last_f3c = 0.0

    while not _stop_event.is_set():
        if any(keyboard.is_pressed(k) for k in STOP_KEYS):
            log("Touche d'arrêt détectée."); break

        now = time.time()
        if now - last_f3c >= F3C_INTERVAL:
            POSX, YAW = f3c_copy()
            last_f3c = now
            if POSX is None or YAW is None:
                continue

            # Lissage
            _x_history.append(POSX)
            if len(_x_history) > SMOOTH_N: _x_history.pop(0)
            Xs = mean(_x_history)

            # Écart
            err = X_TARGET - Xs   # positif → il faut +X ; négatif → il faut -X
            abs_err = abs(err)

            if abs_err <= X_TOLERANCE:
                log(f"X={Xs:.2f} dans la zone cible [{X_TARGET - X_TOLERANCE:.1f} ; {X_TARGET + X_TOLERANCE:.1f}] → aucune correction.")
                continue

            # Direction et touche
            sector = yaw_sector(YAW)
            delta_sign = 1 if err > 0 else -1
            key = key_for_target_deltaX(delta_sign, sector)
            if key is None:
                log(f"YAW={YAW:.1f}° secteur inconnu → skip.")
                continue

            # Durée proportionnelle
            duration = abs_err * STEP_GAIN
            if MAX_STEP is not None: duration = min(duration, MAX_STEP)
            if MIN_STEP is not None: duration = max(duration, MIN_STEP)

            key_name = {VK_Z:'Z', VK_S:'S', VK_Q:'Q', VK_D:'D'}.get(key,'?')
            sens = "+X" if delta_sign > 0 else "-X"
            log(f"Correction: X={Xs:.2f} (cible {X_TARGET:.1f}) err={err:.2f} | YAW={YAW:.1f}°[{sector}] "
                f"→ appui {key_name} {duration:.3f}s (viser {sens})")
            press_key(key, duration)

        time.sleep(0.05)

    release_key(VK_Z)
    log("Arrêt du déplacement.")
    global _running
    _running = False

# =========================
# ===== HOTKEY '+' ========
# =========================
def toggle_run():
    global _running, _thread
    if not _running:
        _stop_event.clear()
        _running = True
        _thread = threading.Thread(target=run_sequence, daemon=True)
        _thread.start()
        log("Séquence lancée (+).")
    else:
        log("Arrêt demandé (+).")
        _stop_event.set()

# =========================
# ======== MAIN ===========
# =========================
def main():
    log("Prêt. '+' pour démarrer/arrêter. Q/Z/S/D/E/T pour stop immédiat.")
    keyboard.add_hotkey('+', toggle_run)
    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        _stop_event.set()
        release_key(VK_Z)
        log("Sortie.")

if __name__ == "__main__":
    main()
