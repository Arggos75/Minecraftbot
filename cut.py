import time
import threading
import keyboard
import win32api
import win32con

# =========================
# ======== CONFIG =========
# =========================

# Déplacements (ZQSD)
COEFF_VITESSE = 1.11
TIME_PER_BLOCK = (4.0 / 19.0) * COEFF_VITESSE

# =========================
# ======== CONFIG =========
# =========================
# Caméra (oscillations verticales)
STEP_SIZE       = 25       # taille de base d’un pas (px)
STEP_DELAY      = 0.002   # délai entre pas (s)
STEP_COEFF      = 1.0     # coefficient appliqué à STEP_SIZE (ex: 1.5 => pas de 7.5px)

AMPLITUDE_BAS   = 600     # amplitude totale vers le bas (px)
AMPLITUDE_HAUT  = 600     # amplitude totale vers le haut (px)
N_MOUVEMENTS    = 20       # nombre d’oscillations (bas + haut)
PAUSE_BETWEEN   = 0.15    # pause entre cycles bas/haut

# Ralenti
SLOW_FACTOR = 2.0         # facteur de ralentissement quand on rappuie sur '+'

# États internes
slow_mode = False

# VK codes
VK_Z  = 0x5A  # avant
VK_LMB = win32con.MOUSEEVENTF_LEFTDOWN
VK_LMB_UP = win32con.MOUSEEVENTF_LEFTUP

# États internes
slow_mode = False


# =========================
# ===== UTILITAIRES =======
# =========================
def log(msg: str):
    print(f"[LOG] {time.strftime('%H:%M:%S')} - {msg}")


# =========================
# ==== CAMÉRA VERTICALE ===
# =========================
def _move_mouse_y_human(dy: int):
    """Déplacement vertical progressif, style humain, avec STEP_COEFF."""
    step = int(round(STEP_SIZE * STEP_COEFF))
    if step <= 0:
        step = 1  # sécurité

    steps = int(abs(dy) / step)
    direction = 1 if dy > 0 else -1
    delay = STEP_DELAY * (SLOW_FACTOR if slow_mode else 1.0)

    for _ in range(steps):
        win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 0, direction * step, 0, 0)
        time.sleep(delay)

    remainder = abs(dy) % step
    if remainder > 0:
        win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 0, direction * remainder, 0, 0)


def camera_oscillations(duration: float):
    """Oscillations caméra pendant une durée donnée."""
    t0 = time.time()
    while time.time() - t0 < duration:
        _move_mouse_y_human(AMPLITUDE_BAS)   # vers le bas
        _move_mouse_y_human(-AMPLITUDE_HAUT) # vers le haut
        # petite pause pour caler le rythme
        time.sleep(0.05)


# =========================
# ===== COMBO ACTION ======
# =========================
def avance_cam_plantee(nb_blocs: float):
    """
    Avance de nb_blocs tout en :
    - tenant clic gauche
    - effectuant des oscillations caméra
    """
    global slow_mode

    duration = nb_blocs * TIME_PER_BLOCK * (SLOW_FACTOR if slow_mode else 1.0)
    log(f"Combo : avance {nb_blocs} blocs (~{duration:.2f}s) avec caméra + clic gauche")

    # maintenir touche avant
    win32api.keybd_event(VK_Z, 0, 0, 0)
    # maintenir clic gauche
    win32api.mouse_event(VK_LMB, 0, 0, 0, 0)

    # thread oscillations caméra
    cam_thread = threading.Thread(target=camera_oscillations, args=(duration,), daemon=True)
    cam_thread.start()

    # attendre la durée
    time.sleep(duration)

    # relâcher
    win32api.keybd_event(VK_Z, 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.mouse_event(VK_LMB_UP, 0, 0, 0, 0)

    log("Fin combo avance+caméra+plantee.")


# =========================
# ======== MAIN ===========
# =========================
def main():
    global slow_mode
    log("Prêt. Appuie sur '+' pour lancer. (Rappuie sur '+' pendant l’exécution pour RALENTIR)")

    keyboard.wait('+')

    def _watch_plus_for_slow():
        global slow_mode
        keyboard.wait('+')
        slow_mode = True
        log("Mode ralenti activé (durées × {:.2f}).".format(SLOW_FACTOR))

    threading.Thread(target=_watch_plus_for_slow, daemon=True).start()

    # ==== Exemple ====
    avance_cam_plantee(23)

    log("Séquence terminée. Programme arrêté.")


if __name__ == "__main__":
    main()
