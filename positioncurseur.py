=========import win32api
import keyboard

print("Appuie sur '=' pour afficher les coordonnées du curseur (Ctrl+C pour quitter)\n")

while True:
    if keyboard.is_pressed('='):
        x, y = win32api.GetCursorPos()
        print(f"x={x}, y={y}")
        # petit délai pour éviter de spammer la console
        keyboard.wait('=')
