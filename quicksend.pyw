"""Double-tap Alt -> tiny box -> message goes to Discord, sent as you.

Drives the running Discord desktop app (Ctrl+K quick switcher + typing), so no
token or bot is needed. Discord must be running (tray is fine).
"""
import ctypes
import os
import queue
import time
import tkinter as tk
from ctypes import wintypes

from pynput import keyboard

TAP_WINDOW = 0.4  # seconds allowed between the two Alt taps
LAST_TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_target.txt")
ALTS = {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr}

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
kb = keyboard.Controller()


class DoubleTap:
    """Fires on two clean Alt taps (no other key in between) within TAP_WINDOW."""

    def __init__(self):
        self.down = False
        self.dirty = False  # another key was touched while/after Alt went down
        self.last_tap = -1.0

    def feed(self, pressed, is_alt, t):
        if not is_alt:
            self.dirty = True
            self.last_tap = -1.0
            return False
        if pressed:
            if not self.down:  # ignore key-repeat
                self.down, self.dirty = True, False
            return False
        self.down = False
        if self.dirty:
            return False
        if t - self.last_tap <= TAP_WINDOW:
            self.last_tap = -1.0
            return True
        self.last_tap = t
        return False


def find_discord():
    """Main window of Discord.exe (also finds it when hidden in the tray)."""
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, 512)
        if not title.value.endswith("Discord"):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if h:
            path = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            kernel32.QueryFullProcessImageNameW(h, 0, path, ctypes.byref(size))
            kernel32.CloseHandle(h)
            if path.value.lower().endswith("discord.exe"):
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def tap(key):
    kb.press(key)
    kb.release(key)


def send_to_discord(target, message):
    hwnd = find_discord()
    if not hwnd:
        return "Discord isn't running"
    was_visible = user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd)
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.4)
    if user32.GetForegroundWindow() != hwnd:
        return "Couldn't focus Discord"
    if target:
        with kb.pressed(keyboard.Key.ctrl):
            tap("k")
        time.sleep(0.3)
        kb.type(target)
        time.sleep(0.6)  # let the switcher rank results
        tap(keyboard.Key.enter)
        time.sleep(0.6)
    for i, line in enumerate(message.split("\n")):
        if i:
            with kb.pressed(keyboard.Key.shift):  # newline without sending
                tap(keyboard.Key.enter)
        kb.type(line)
    tap(keyboard.Key.enter)
    time.sleep(0.2)
    if not was_visible:
        user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE, put it back out of the way
    return None


class Popup:
    def __init__(self):
        self.events = queue.Queue()
        self.root = root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg="#313338", padx=10, pady=10)

        font = ("Segoe UI", 13)
        self.msg = tk.Text(root, width=48, height=1, font=font, bg="#383a40", fg="#dbdee1",
                           insertbackground="#dbdee1", relief="flat", padx=8, pady=6, wrap="word")
        self.msg.grid(row=0, column=0, sticky="nsew")
        tk.Label(root, text="to", font=("Segoe UI", 10), bg="#313338", fg="#949ba4").grid(row=0, column=1, padx=(10, 4))
        self.to = tk.Entry(root, width=16, font=font, bg="#383a40", fg="#dbdee1",
                           insertbackground="#dbdee1", relief="flat")
        self.to.grid(row=0, column=2, sticky="ns", ipady=6)
        self.status = tk.Label(root, text="", font=("Segoe UI", 9), bg="#313338", fg="#f23f43")
        self.status.grid(row=1, column=0, columnspan=3, sticky="w")
        if os.path.exists(LAST_TARGET):
            with open(LAST_TARGET, encoding="utf-8") as f:
                self.to.insert(0, f.read().strip())

        for w in (self.msg, self.to):
            w.bind("<Return>", self.submit)
            w.bind("<Escape>", lambda e: self.hide())
        self.msg.bind("<Shift-Return>", lambda e: self.grow())
        root.bind("<FocusOut>", lambda e: root.after(100, self.hide_if_unfocused))

        detector = DoubleTap()
        on = lambda pressed: lambda k: detector.feed(pressed, k in ALTS, time.monotonic()) and self.events.put("show")
        keyboard.Listener(on_press=on(True), on_release=on(False), daemon=True).start()
        root.after(50, self.poll)

    def poll(self):
        while not self.events.empty():
            self.events.get()
            self.show()
        self.root.after(50, self.poll)

    def grow(self):
        lines = int(self.msg.index("end-1c").split(".")[0]) + 1
        self.msg.configure(height=min(lines, 8))

    def show(self):
        r = self.root
        self.status.configure(text="")
        r.deiconify()
        r.update_idletasks()
        x = (r.winfo_screenwidth() - r.winfo_width()) // 2
        r.geometry(f"+{x}+{r.winfo_screenheight() // 4}")
        r.lift()
        r.focus_force()
        self.msg.focus_set()

    def hide(self):
        self.root.withdraw()

    def hide_if_unfocused(self):
        if self.root.focus_get() is None:
            self.hide()

    def submit(self, _):
        message = self.msg.get("1.0", "end-1c").strip()
        target = self.to.get().strip()
        if not message:
            return "break"
        self.hide()
        err = send_to_discord(target, message)
        if err:
            self.show()
            self.status.configure(text=err)
            return "break"
        self.msg.delete("1.0", "end")
        self.msg.configure(height=1)
        with open(LAST_TARGET, "w", encoding="utf-8") as f:
            f.write(target)
        return "break"


if __name__ == "__main__":
    Popup().root.mainloop()
