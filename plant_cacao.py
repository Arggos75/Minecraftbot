import time
import threading
import keyboard
import win32api
import win32con
import pyperclip
import re

# =========================
# ======== CONFIG =========
# =========================
# Caméra (pitch)
SENSITIVITY_COEFF = 8.0     # conversion degrés -> pixels souris
STEP_SIZE = 5               # déplacement progressif (px) pour effet "humain"
STEP_DELAY = 0.003          # délai entre mini-pas
MIN_F3C_INTERVAL = 0.30     # >= 250 ms
COPY_SETTLE = 0.06          # temps pour que le presse-papier soit rempli

# Déplacements (ZQSD)
COEFF_VITESSE = 1.11        # calibré pour ~19 blocs en 4 s
TIME_PER_BLOCK = (4.0 / 19.0) * COEFF_VITESSE

# VK codes
VK_F3 = 0x72
VK_C  = 0x43
VK_Q  = 0x51  # gauche
VK_S  = 0x53  # arrière
VK_D  = 0x44  # droite
VK_Z  = 0x5A  # avant

# États internes
last_f3c_time = 0.0

# --- État d'exécution de séquence ---
_running_lock = threading.Lock()
_running = False                     # True si une séquence est en cours
_stop_event = threading.Event()      # signal d'arrêt (via '+', ou Z/Q/S/D)
_seq_thread = None                   # thread courant de séquence

# Pour ignorer les touches simulées lors du test de stop
_simulated_keys_active = set()       # {'q','s','d','z'}


# =========================
# ===== UTILITAIRES =======
# =========================
def log(msg: str):
    print(f"[LOG] {time.strftime('%H:%M:%S')} - {msg}")

def _sleep_check(total_s: float, step: float = 0.01) -> bool:
    """Dors par petits pas en vérifiant l'arrêt. Retourne True si arrêt demandé."""
    end = time.time() + total_s
    while time.time() < end:
        if _should_stop():
            return True
        time.sleep(min(step, end - time.time()))
    return _should_stop()

def _any_stop_key_pressed() -> bool:
    """Détecte un appui utilisateur réel sur Q/S/D/Z (ignorant les touches simulées en cours)."""
    # NB: si on simule 'q', l'utilisateur peut encore presser s/d/z pour interrompre.
    for key in ('q', 's', 'd', 'z'):
        if key in _simulated_keys_active:
            continue
        try:
            if keyboard.is_pressed(key):
                return True
        except:
            # Sur certains environnements, keyboard peut lever des erreurs sporadiques
            pass
    return False

def _should_stop() -> bool:
    """Vrai si l'arrêt est demandé (event) ou si l'utilisateur presse Z/Q/S/D."""
    if _stop_event.is_set():
        return True
    if _any_stop_key_pressed():
        request_stop("Touche Z/Q/S/D pressée")
        return True
    return False

def request_stop(reason: str = ""):
    """Déclenche l'arrêt (idempotent) et relâche la plantée."""
    if not _stop_event.is_set():
        _stop_event.set()
        try:
            arret_plantee()
        except Exception:
            pass
        log("Séquence: arrêt demandé" + (f" ({reason})" if reason else ""))


# =========================
# ===== F3+C / CLIP =======
# =========================
def _throttle_f3c():
    """Respecte l'intervalle minimal entre deux F3+C."""
    global last_f3c_time
    now = time.time()
    dt = now - last_f3c_time
    if dt < MIN_F3C_INTERVAL:
        _sleep_check(MIN_F3C_INTERVAL - dt)

def _f3c_copy():
    """Déclenche F3+C (throttle) et attend le clipboard."""
    global last_f3c_time
    if _should_stop():
        return
    _throttle_f3c()
    if _should_stop():
        return

    win32api.keybd_event(VK_F3, 0, 0, 0)
    win32api.keybd_event(VK_C,  0, 0, 0)
    _sleep_check(0.05)
    win32api.keybd_event(VK_C,  0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(VK_F3, 0, win32con.KEYEVENTF_KEYUP, 0)
    last_f3c_time = time.time()
    _sleep_check(COPY_SETTLE)

def _parse_execute_line(text: str):
    """
    Parse '/execute ... tp @s X Y Z YAW PITCH' -> (x, y, z, yaw, pitch) floats
    """
    m = re.search(
        r"/execute\s+.*?\s+tp\s+@s\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)",
        text
    )
    if not m:
        return None
    return tuple(float(v) for v in m.groups())

def read_pitch():
    """Lit le pitch (souris Y) via F3+C."""
    _f3c_copy()
    if _should_stop():
        return None
    parsed = _parse_execute_line(pyperclip.paste())
    if not parsed:
        return None
    return parsed[-1]  # pitch


# =========================
# ==== CAMÉRA (PITCH) =====
# =========================
def _move_mouse_y_human(dy: int):
    """Déplacement vertical progressif, style humain, interrompable."""
    steps = int(abs(dy) / STEP_SIZE)
    direction = 1 if dy > 0 else -1
    for _ in range(steps):
        if _should_stop():
            return
        win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 0, direction * STEP_SIZE, 0, 0)
        if _sleep_check(STEP_DELAY):
            return
    remainder = abs(dy) % STEP_SIZE
    if remainder > 0 and not _should_stop():
        win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 0, direction * remainder, 0, 0)

def _choose_target_pitch(pitch: float, lo: float, hi: float) -> float:
    """Retourne la borne la plus proche si hors zone, sinon le pitch courant."""
    if lo <= pitch <= hi:
        return pitch
    return lo if abs(pitch - lo) < abs(pitch - hi) else hi

def adjust_pitch(min_pitch: float, max_pitch: float):
    if _should_stop():
        return

    pitch0 = read_pitch()
    if pitch0 is None:
        if not _stop_event.is_set():
            log("Impossible de lire le pitch initial.")
        return

    if min_pitch <= pitch0 <= max_pitch:
        log(f"Déjà dans la zone [{min_pitch}, {max_pitch}] → {pitch0:.2f}")
        return

    target = _choose_target_pitch(pitch0, min_pitch, max_pitch)
    delta_pitch = target - pitch0
    dy = int(round(delta_pitch * SENSITIVITY_COEFF))  # dy>0 = souris descend (pitch augmente)
    log(f"Pitch={pitch0:.2f} → cible={target:.2f} | déplacement prévu dy={dy}px")
    _move_mouse_y_human(dy)
    if _should_stop():
        return

    pitch1 = read_pitch()
    if pitch1 is None:
        if not _stop_event.is_set():
            log("Impossible de lire le pitch final.")
        return

    ok = (min_pitch <= pitch1 <= max_pitch)
    log(f"Pitch final={pitch1:.2f} → {'OK (dans la zone)' if ok else 'HORS zone'}")


# ----- API de recentrage caméra -----
def recentrage_camera_ligne_haut():
    """Zone haute : [-35 ; -18]"""
    adjust_pitch(-35.0, -18.0)

def recentrage_camera_centrale():
    """Zone centrale : [-6 ; 15]"""
    adjust_pitch(-6.0, 15.0)

def recentrage_camera_ligne_bas():
    """Zone basse : [32 ; 44]"""
    adjust_pitch(32.0, 44.0)


# =========================
# ===== DÉPLACEMENTS ======
# =========================
def _press_key(vk_code: int, duration: float):
    """Maintient une touche pendant 'duration' en restant interrompable."""
    if _should_stop():
        return

    # marquer la touche simulée (pour ne pas la confondre avec un appui utilisateur)
    name = None
    if vk_code == VK_Q: name = 'q'
    elif vk_code == VK_S: name = 's'
    elif vk_code == VK_D: name = 'd'
    elif vk_code == VK_Z: name = 'z'
    if name:
        _simulated_keys_active.add(name)

    try:
        win32api.keybd_event(vk_code, 0, 0, 0)
        t0 = time.time()
        while time.time() - t0 < duration:
            if _should_stop():
                break
            time.sleep(0.01)
    finally:
        win32api.keybd_event(vk_code, 0, win32con.KEYEVENTF_KEYUP, 0)
        if name:
            _simulated_keys_active.discard(name)

def _duration_for_blocks(nb_blocs: float) -> float:
    return nb_blocs * TIME_PER_BLOCK

def deplacement_gauche(nb_blocs: float):
    duration = _duration_for_blocks(nb_blocs)
    log(f"← Gauche {nb_blocs} blocs ({duration:.2f}s)")
    _press_key(VK_Q, duration)

def deplacement_droite(nb_blocs: float):
    duration = _duration_for_blocks(nb_blocs)
    log(f"→ Droite {nb_blocs} blocs ({duration:.2f}s)")
    _press_key(VK_D, duration)

def deplacement_avant(nb_blocs: float):
    duration = _duration_for_blocks(nb_blocs)
    log(f"↑ Avant {nb_blocs} blocs ({duration:.2f}s)")
    _press_key(VK_Z, duration)

def deplacement_arriere(nb_blocs: float):
    duration = _duration_for_blocks(nb_blocs)
    log(f"↓ Arrière {nb_blocs} blocs ({duration:.2f}s)")
    _press_key(VK_S, duration)


# =========================
# ====== PLANTÉE ==========
# =========================
def plantee():
    """Maintient le clic RIGHT (plantée)."""
    # NOTE: ton script d'origine utilisait RIGHTDOWN/RIGHTUP mais log 'clic gauche'.
    # Je garde le comportement d'origine (RIGHT) pour rester strictement fidèle.
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
    log("Clic RIGHT maintenu (plantée).")

def arret_plantee():
    """Relâche le clic RIGHT (arrêt plantée)."""
    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
    log("Clic RIGHT relâché (arrêt plantée).")


# =========================
# ====== SÉQUENCE =========
# =========================
def _sequence():
    """La séquence de démo – interrompable à tout moment."""
    log("Séquence démarrée.")
    try:
        if _should_stop(): return
        recentrage_camera_ligne_haut()
        if _should_stop(): return

        plantee()
        if _should_stop(): return

        deplacement_gauche(70)
        if _should_stop(): return

        recentrage_camera_centrale()
        if _should_stop(): return

        deplacement_droite(70)
        if _should_stop(): return

        recentrage_camera_ligne_bas()
        if _should_stop(): return

        deplacement_gauche(70)
        if _should_stop(): return

        arret_plantee()
        if _should_stop(): return

        log("Séquence terminée.")
    finally:
        # Nettoyage de fin si arrêt demandé en cours de route
        if _stop_event.is_set():
            log("Séquence interrompue.")
        # Libérer l'état 'running'
        global _running
        with _running_lock:
            _running = False


# =========================
# ======== MAIN ===========
# =========================
def _on_plus():
    """Hotkey '+': toggle start/stop de la séquence."""
    global _running, _seq_thread
    with _running_lock:
        if not _running:
            # démarrage
            _stop_event.clear()
            log("Appui '+' → lancement de la séquence.")
            _running = True
            _seq_thread = threading.Thread(target=_sequence, daemon=True)
            _seq_thread.start()
        else:
            # arrêt
            log("Appui '+' → arrêt de la séquence en cours.")
            request_stop("Touche '+' pressée")

def main():
    log("Prêt. '+' pour lancer/arrêter la séquence. Q/S/D/Z → arrêt immédiat pendant la séquence.")
    # Hotkey principal
    keyboard.add_hotkey('+', _on_plus)

    # Boucle de maintien du programme en vie
    # (on peut quitter avec Ctrl+C dans la console)
    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        request_stop("CTRL+C")
        log("Sortie.")

if __name__ == "__main__":
    main()
