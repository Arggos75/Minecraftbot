import keyboard
import win32api
import win32api, win32con, time

print("➡️ Appuie sur ta touche qui fait '/' et regarde le code ici :")

event = keyboard.read_event()
if event.event_type == keyboard.KEY_DOWN:
    VK_ESCAPE = 0x1B  # touche Échap
    # Appuie puis relâche
    win32api.keybd_event(VK_ESCAPE, 0, 0, 0)
    time.sleep(0.05)
    win32api.keybd_event(VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)