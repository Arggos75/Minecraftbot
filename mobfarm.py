# mobfarm.py — autoclick + déplacements asymétriques (retour exact à la position)
import time
import threading
import random
import keyboard
import win32api, win32con

# ===========================
# CONFIG
# ===========================
CPS = 10
CLICK_INTERVAL = 1.0 / CPS
RANDOM_PAUSE_MIN = 10.0
RANDOM_PAUSE_MAX = 20.0
MOVE_DURATION_MIN = 0.1   # X min
MOVE_DURATION_MAX = 0.2   # X max

# Déplacements (AZERTY Minecraft)
MOVE_KEYS_VK = {
    "forward": ord('Z'),  # haut
    "back":    ord('S'),  # bas
    "left":    ord('Q'),
    "right":   ord('D'),
}

TOGGLE_KEY = "+"       # toggle autoclick
EMERGENCY_STOPS = ["a", "e"]  # arrêts d'urgence (libres, pas ZQSD)

# ===========================
# ÉTAT GLOBAL
# ===========================
running = False
_pause_flag = False
_lock = threading.Lock()

# ===========================
# UTILITAIRES
# ===========================
def left_click():
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.03)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

def vk_hold(duration, vk_code):
    """Maintient la touche vk_code pendant 'duration' secondes."""
    if duration <= 0:
        return
    win32api.keybd_event(vk_code, 0, 0, 0)
    t0 = time.time()
    while time.time() - t0 < duration:
        time.sleep(0.01)
    win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)

# ===========================
# AUTOCLICK
# ===========================
def attack_loop():
    global running, _pause_flag
    print(f"Autoclick prêt ({CPS} cps). '+' pour démarrer/arrêter.", flush=True)
    while running:
        with _lock:
            paused = _pause_flag
        if not paused:
            # petit lot de clics pour lisser la charge
            for _ in range(5):
                if not running or _pause_flag:
                    break
                left_click()
                time.sleep(CLICK_INTERVAL)
        else:
            time.sleep(0.02)
    print("[Autoclick] Arrêté.", flush=True)

def toggle_attack():
    global running
    if not running:
        running = True
        threading.Thread(target=attack_loop, daemon=True).start()
        print("[Autoclick] Démarré.", flush=True)
    else:
        running = False
        print("[Autoclick] Arrêt demandé.", flush=True)

def emergency_stop():
    global running
    running = False
    print("⛔ Arrêt d'urgence.", flush=True)

# ===========================
# DÉPLACEMENTS ASYMÉTRIQUES (X, 2X, X)
# ===========================
def perform_vertical_then_horizontal():
    """Pause l'attaque, fait (Z X) → (S 2X) → (Z X), puis (Q X) → (D 2X) → (Q X)."""
    global _pause_flag
    with _lock:
        if not running:
            return
        _pause_flag = True
    print("[MVT] Pause attaque → déplacements…", flush=True)

    # Tirage X (vertical)
    Xv = random.uniform(MOVE_DURATION_MIN, MOVE_DURATION_MAX)
    print(f"[MVT] Vertical: Z {Xv:.3f}s → S {2*Xv:.3f}s → Z {Xv:.3f}s", flush=True)
    vk_hold(Xv, MOVE_KEYS_VK["forward"])     # Z (haut)
    time.sleep(0.03)
    vk_hold(2 * Xv, MOVE_KEYS_VK["back"])    # S (bas)
    time.sleep(0.03)
    vk_hold(Xv, MOVE_KEYS_VK["forward"])     # Z (haut)

    time.sleep(0.08)
    """
    # Tirage X (horizontal)
    Xh = random.uniform(MOVE_DURATION_MIN, MOVE_DURATION_MAX)
    print(f"[MVT] Horizontal: Q {Xh:.3f}s → D {2*Xh:.3f}s → Q {Xh:.3f}s", flush=True)
    vk_hold(Xh, MOVE_KEYS_VK["left"])        # Q (gauche)
    time.sleep(0.03)
    vk_hold(2 * Xh, MOVE_KEYS_VK["right"])   # D (droite)
    time.sleep(0.03)
    vk_hold(Xh, MOVE_KEYS_VK["left"])        # Q (gauche)
    """

    with _lock:
        _pause_flag = False
    print("[MVT] Déplacements terminés → reprise de l'attaque.", flush=True)

# ===========================
# SCHEDULER
# ===========================
def scheduler_loop():
    print("[SCHED] Actif (10–20 s aléatoires). Premier déclenchement dans 3 s.", flush=True)
    time.sleep(3.0)  # test initial rapide
    while True:
        wait_t = random.uniform(RANDOM_PAUSE_MIN, RANDOM_PAUSE_MAX)
        print(f"[SCHED] Prochain mouvement dans {wait_t:.1f}s", flush=True)
        time.sleep(wait_t)
        with _lock:
            should_move = running and not _pause_flag
        if should_move:
            print("[SCHED] Déclenchement mouvement asymétrique", flush=True)
            threading.Thread(target=perform_vertical_then_horizontal, daemon=True).start()
        else:
            print("[SCHED] Attaque inactive ou déjà en pause → skip.", flush=True)

# ===========================
# HOTKEYS
# ===========================
keyboard.add_hotkey(TOGGLE_KEY, toggle_attack)
for key in EMERGENCY_STOPS:
    keyboard.add_hotkey(key, emergency_stop)

# ===========================
# MAIN
# ===========================
threading.Thread(target=scheduler_loop, daemon=True).start()
print("Programme prêt. '+' pour activer l’autoclick. (Z/S/Q/D = déplacement)", flush=True)
keyboard.wait()
