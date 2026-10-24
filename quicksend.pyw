"""quickcord: double-tap Alt -> small box -> Discord message, sent as you.

Talks to Discord's API with your user token (token.txt next to this file).
"""
import ctypes
import json
import os
import time
import urllib.error
import urllib.request

import pystray
import webview
from PIL import Image, ImageDraw
from pynput import keyboard

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(HERE, "token.txt")
API = "https://discord.com/api/v9"
TAP_WINDOW = 0.4  # seconds allowed between the two Alt taps
WIDTH, HEIGHT, MAX_HEIGHT = 680, 70, 480
ALTS = {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr}

user32 = ctypes.windll.user32


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


class DiscordError(Exception):
    pass


def discord(method, path, body=None):
    if not os.path.exists(TOKEN_FILE):
        raise DiscordError("Put your Discord token in token.txt (see README)")
    with open(TOKEN_FILE, encoding="utf-8") as f:
        token = f.read().strip()
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": token, "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise DiscordError("Discord rejected the token in token.txt")
        if e.code == 429:
            raise DiscordError("Discord is rate limiting, try again in a few seconds")
        raise DiscordError(f"Discord error {e.code}: {e.read().decode(errors='replace')[:200]}")
    except urllib.error.URLError as e:
        raise DiscordError(f"Couldn't reach Discord: {e.reason}")


def recent_chats(channels):
    """DMs and group DMs, newest message first, in the shape the UI wants."""
    chats = []
    for c in channels:
        users = c.get("recipients", [])
        if c["type"] == 1 and users:
            u = users[0]
            name = u.get("global_name") or u["username"]
            avatar = (f"https://cdn.discordapp.com/avatars/{u['id']}/{u['avatar']}.png?size=64" if u.get("avatar")
                      else f"https://cdn.discordapp.com/embed/avatars/{(int(u['id']) >> 22) % 6}.png")
        elif c["type"] == 3:
            name = c.get("name") or ", ".join(u.get("global_name") or u["username"] for u in users) or "Group"
            avatar = (f"https://cdn.discordapp.com/channel-icons/{c['id']}/{c['icon']}.png?size=64" if c.get("icon")
                      else "https://cdn.discordapp.com/embed/avatars/0.png")
        else:
            continue
        chats.append({"id": c["id"], "name": name, "avatar": avatar, "last": int(c.get("last_message_id") or 0)})
    chats.sort(key=lambda c: c["last"], reverse=True)
    return chats


class Api:
    """Called from ui.html via window.pywebview.api.*"""

    def __init__(self):
        self._window = None

    def chats(self):
        try:
            return {"chats": recent_chats(discord("GET", "/users/@me/channels"))}
        except DiscordError as e:
            return {"error": str(e)}

    def send(self, channel_id, text):
        if not text.strip() or len(text) > 2000:
            return {"error": "Messages must be 1 to 2000 characters"}
        try:
            discord("POST", f"/channels/{channel_id}/messages", {"content": text})
            return {}
        except DiscordError as e:
            return {"error": str(e)}

    def resize(self, height):
        self._window.resize(WIDTH, max(HEIGHT, min(int(height), MAX_HEIGHT)))

    def hide(self):
        self._window.hide()


def force_foreground(hwnd):
    # Windows only lets the app that made the last input take focus, so make a harmless Alt press ourselves
    user32.keybd_event(0x12, 0, 1, 0)  # VK_MENU down, extended
    user32.ShowWindow(hwnd, 5)  # SW_SHOW
    user32.SetForegroundWindow(hwnd)
    user32.keybd_event(0x12, 0, 3, 0)  # VK_MENU up


def main():
    api = Api()
    window = webview.create_window("quickcord", os.path.join(HERE, "ui.html"), js_api=api, width=WIDTH, height=HEIGHT,
                                   frameless=True, on_top=True, hidden=True, background_color="#313338")
    api._window = window

    def show():
        screen = webview.screens[0]
        window.resize(WIDTH, HEIGHT)
        window.move((screen.width - WIDTH) // 2, screen.height // 4)
        window.show()
        hwnd = user32.FindWindowW(None, "quickcord")
        if hwnd:
            corner = ctypes.c_int(2)  # DWMWCP_ROUND, Windows 11 rounded corners
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), 4)
            force_foreground(hwnd)
        window.evaluate_js("onShow()")

    def started():
        detector = DoubleTap()

        def on(pressed):
            def handler(k):  # must return None: pynput stops the listener if a callback returns False
                if detector.feed(pressed, k in ALTS, time.monotonic()):
                    show()
            return handler

        keyboard.Listener(on_press=on(True), on_release=on(False), daemon=True).start()

        img = Image.new("RGBA", (64, 64))
        ImageDraw.Draw(img).ellipse((4, 4, 60, 60), fill="#5865f2")
        pystray.Icon("quickcord", img, "quickcord (double-tap Alt)", pystray.Menu(
            pystray.MenuItem("Open", lambda: show(), default=True),
            pystray.MenuItem("Quit", lambda icon: (icon.stop(), window.destroy())),
        )).run_detached()

    webview.start(started)


if __name__ == "__main__":
    main()
