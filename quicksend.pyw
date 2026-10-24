"""quickcord: double-tap Alt -> small box -> Discord message, sent as you.

Talks to Discord's API as you. The first run opens Discord's login page and saves the token,
encrypted to your Windows account, in %APPDATA%\\quickcord.
"""
import ctypes
import json
import os
import threading
import time
import urllib.error
import urllib.request
from ctypes import wintypes

import pystray
import webview
from PIL import Image, ImageDraw
from pynput import keyboard

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(os.environ["APPDATA"], "quickcord", "token.dat")
API = "https://discord.com/api/v9"
TAP_WINDOW = 0.4  # seconds allowed between the two Alt taps
WIDTH, HEIGHT, MAX_HEIGHT = 680, 70, 480
ALTS = {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr}

user32 = ctypes.windll.user32


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(fn, data):
    """Windows DPAPI: only your Windows account on this PC can decrypt."""
    buf = ctypes.create_string_buffer(data, len(data))
    out = _Blob()
    if not fn(ctypes.byref(_Blob(len(data), buf)), None, None, None, None, 0, ctypes.byref(out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def save_token(token):
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, "wb") as f:
        f.write(_dpapi(ctypes.windll.crypt32.CryptProtectData, token.encode()))


def load_token():
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, "rb") as f:
        try:
            return _dpapi(ctypes.windll.crypt32.CryptUnprotectData, f.read()).decode()
        except OSError:  # corrupted, or copied from another PC/account
            return None


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
    token = load_token()
    if not token:
        raise DiscordError("Not logged in: right-click the tray icon and pick Log in")
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
            raise DiscordError("Logged out of Discord: right-click the tray icon and pick Log in")
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
        if not (isinstance(channel_id, str) and channel_id.isdigit()):  # it goes into the URL path
            return {"error": "Pick a conversation"}
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
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


# Discord hides window.localStorage on its pages, but a fresh iframe still has it
READ_TOKEN_JS = """(() => { try {
  const f = document.body.appendChild(document.createElement('iframe'));
  const t = f.contentWindow.localStorage.getItem('token'); f.remove(); return t;
} catch (e) { return null } })()"""


def login():
    """Opens Discord's own login page and saves the token once you're signed in."""
    win = webview.create_window("Log in to Discord - quickcord", "https://discord.com/login", width=1000, height=760)
    closed = []
    win.events.closed += lambda: closed.append(True)
    while not closed:
        time.sleep(1)
        try:
            # only trust a token read from discord.com itself, not a page it navigated to
            if not (win.get_current_url() or "").startswith("https://discord.com/"):
                continue
            raw = win.evaluate_js(READ_TOKEN_JS)
        except Exception:  # page still loading or mid-navigation
            continue
        if raw:
            save_token(json.loads(raw))
            win.destroy()
            return


def force_foreground(hwnd):
    # Windows only lets the app that made the last input take focus, so make a harmless Alt press ourselves
    user32.keybd_event(0x12, 0, 1, 0)  # VK_MENU down, extended
    user32.ShowWindow(hwnd, 5)  # SW_SHOW
    user32.SetForegroundWindow(hwnd)
    user32.keybd_event(0x12, 0, 3, 0)  # VK_MENU up


def main():
    api = Api()
    # inline html, not a file path: a path makes pywebview serve this whole folder on localhost
    with open(os.path.join(HERE, "ui.html"), encoding="utf-8") as f:
        html = f.read()
    window = webview.create_window("quickcord", html=html, js_api=api, width=WIDTH, height=HEIGHT,
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
            pystray.MenuItem("Log in", lambda: threading.Thread(target=login, daemon=True).start()),
            pystray.MenuItem("Quit", lambda icon: (icon.stop(), window.destroy())),
        )).run_detached()

        if not load_token():
            login()

    webview.start(started)


if __name__ == "__main__":
    main()
