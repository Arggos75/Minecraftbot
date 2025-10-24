import time
import random
import threading
import keyboard
import win32api, win32con

# === CONFIGURATION ===
CLICKS_PER_SECOND = 6        # ⚙️ vitesse moyenne (clics/sec) — change ici
PAUSE_CHANCE = 0.01          # ⚙️ probabilité de faire une pause après un clic (1% = rare)
PAUSE_DURATION = (0.2, 0.5)  # ⚙️ durée min/max d'une pause "humaine"

# === Touches ===
VK_Q = 0x51
VK_S = 0x53
VK_D = 0x44
VK_Z = 0x5A
VK_PLUS = 0xBB  # touche '+'

# === État global ===
_running_lock = threading.Lock()
_running = False
_stop_event = threading.Event()
_click_thread = None


# --- Fonctions de base ---

def _any_stop_key_pressed() -> bool:
    """Vrai si Z, S, Q ou D pressée."""
    for key in ('t', 'e'):
        try:
            if keyboard.is_pressed(key):
                return True
        except:
            pass
    return False

def _should_stop() -> bool:
    if _stop_event.is_set():
        return True
    if _any_stop_key_pressed():
        request_stop("Touche Z/S/Q/D pressée")
        return True
    return False

def request_stop(reason: str = ""):
    """Déclenche l'arrêt global."""
    global _running
    if not _stop_event.is_set():
        _stop_event.set()
        print("Autoclick: arrêt demandé" + (f" ({reason})" if reason else ""))
    with _running_lock:
        _running = False


# --- Autoclick ---

def click_left():
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(random.uniform(0.005, 0.015))
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

def _autoclick_loop():
    """Boucle principale d'autoclick humain."""
    print(f"[Autoclick] Démarré ({CLICKS_PER_SECOND} cps)")
    base_interval = 1 / CLICKS_PER_SECOND

    try:
        while not _should_stop():
            click_left()

            # délai moyen autour de la cible
            jitter = random.uniform(-0.015, 0.015)
            interval = max(0.03, base_interval + jitter)

            # pause humaine (rare)
            if random.random() < PAUSE_CHANCE:
                pause = random.uniform(*PAUSE_DURATION)
                print(f"[Autoclick] Pause humaine {pause:.2f}s")
                time.sleep(pause)

            time.sleep(interval)
    finally:
        print("[Autoclick] Arrêté.")
        with _running_lock:
            global _running
            _running = False


# --- Gestion touche '+' ---

def _on_plus():
    global _running, _click_thread
    with _running_lock:
        if not _running:
            _stop_event.clear()
            print("Appui '+' → démarrage de l’autoclick.")
            _running = True
            _click_thread = threading.Thread(target=_autoclick_loop, daemon=True)
            _click_thread.start()
        else:
            print("Appui '+' → arrêt de l’autoclick.")
            request_stop("Touche '+' pressée")


# --- Main loop ---

def main():
    print("Autoclick prêt. '+' pour démarrer/arrêter, Z/S/Q/D pour stop d'urgence.")
    print(f"Vitesse actuelle : {CLICKS_PER_SECOND} clics/seconde.")
    keyboard.add_hotkey('+', _on_plus)

    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        request_stop("CTRL+C")
        print("Sortie.")


if __name__ == "__main__":
    main()
