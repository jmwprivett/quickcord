"""quickcord: double-tap Alt (Option on macOS) -> small box -> Discord message, sent as you.

Talks to Discord's API as you. The first run opens Discord's login page and saves the token:
on Windows encrypted to your account in %APPDATA%\\quickcord, on macOS in the login Keychain.
"""
import ctypes
import importlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from ctypes import wintypes

import pystray
import webview
from PIL import Image
from pynput import keyboard

MAC = sys.platform == "darwin"
HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://discord.com/api/v9"
TAP_WINDOW = 0.4  # seconds allowed between the two Alt taps
WIN_OPACITY = 0.83  # Windows can't show the page's own see-through without blurring, so the whole window is see-through
# on macOS the window is transparent and ui.html keeps a 16px margin around its panel for the shadow;
# on Windows the panel fills the window and the OS draws the glass, corners and shadow
MARGIN = 16 if MAC else 0
WIDTH, HEIGHT, MAX_HEIGHT = 680 + 2 * MARGIN, 70 + 2 * MARGIN, 480 + 2 * MARGIN
ALTS = {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr}
TRAY = "click the menu bar icon" if MAC else "right-click the tray icon"

if MAC:
    import AppKit
    import keyring
    import keyring.backends.macOS
    import keyring.errors
    import Quartz
    from PyObjCTools import AppHelper

    KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT = "quickcord", "token"

    def _keychain():
        # keyring falls back to other backends (some write plain files), so insist on the real Keychain
        backend = keyring.get_keyring()
        if not isinstance(backend, keyring.backends.macOS.Keyring):
            raise RuntimeError(f"Expected the macOS Keychain, got keyring backend {type(backend).__name__}")
        return backend

    def save_token(token):
        _keychain().set_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT, token)

    def load_token():
        try:
            return _keychain().get_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)
        except (keyring.errors.KeyringError, RuntimeError):  # locked keychain, access denied, wrong backend
            return None

    def delete_token():
        try:
            _keychain().delete_password(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)
        except keyring.errors.PasswordDeleteError:  # already gone
            pass
else:
    TOKEN_FILE = os.path.join(os.environ["APPDATA"], "quickcord", "token.dat")
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

    def delete_token():
        try:
            os.remove(TOKEN_FILE)
        except FileNotFoundError:
            pass


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
        raise DiscordError(f"Not logged in: {TRAY} and pick Log in")
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
            raise DiscordError(f"Logged out of Discord: {TRAY} and pick Log in")
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
        if not MAC:
            fade(self._window, WIN_OPACITY, 0)  # on macOS ui.html already faded the panel out
        self._window.hide()


# Discord hides window.localStorage on its pages, but a fresh iframe still has it
READ_TOKEN_JS = """(() => { try {
  const f = document.body.appendChild(document.createElement('iframe'));
  const t = f.contentWindow.localStorage.getItem('token'); f.remove(); return t;
} catch (e) { return null } })()"""


def login():
    """Opens Discord's own login page and saves the token once you're signed in."""
    win = webview.create_window("Log in to Discord - quickcord", "https://discord.com/login", width=1000, height=760)
    if MAC:  # a menu bar app isn't active by default, so pull the login window to the front
        win.events.shown += activate_mac
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


def light_theme():
    """True when the Windows taskbar is light, so the tray icon should be black."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "SystemUsesLightTheme")[0] == 1  # taskbar theme, separate from apps
    except OSError:
        return False  # older Windows: dark taskbar


def menu_bar_image():
    """The black logo as a template image: macOS tints it for light/dark and wallpaper-tinted menu bars, live."""
    image = AppKit.NSImage.alloc().initWithContentsOfFile_(os.path.join(HERE, "light-icon.png"))
    image.setSize_((18, 18))  # points; the 512px original stays as the bitmap, so it's sharp on Retina
    image.setTemplate_(True)
    return image


def force_foreground(hwnd):
    # Windows only lets the app that made the last input take focus, so make a harmless Alt press ourselves
    user32.keybd_event(0x12, 0, 1, 0)  # VK_MENU down, extended
    user32.ShowWindow(hwnd, 5)  # SW_SHOW
    user32.SetForegroundWindow(hwnd)
    # a lone Alt release puts the window in menu mode, which blurs the page and closes the box;
    # an unassigned key in between (AutoHotkey's "menu mask" trick) makes it an Alt+key combo instead
    user32.keybd_event(0xE8, 0, 0, 0)
    user32.keybd_event(0xE8, 0, 2, 0)
    user32.keybd_event(0x12, 0, 3, 0)  # VK_MENU up


def on_ui_thread(window, fn):
    from System import Action  # pythonnet, which pywebview uses on Windows
    window.native.Invoke(Action(fn))


class _Margins(ctypes.Structure):
    _fields_ = [(side, ctypes.c_int) for side in ("left", "right", "top", "bottom")]


def glass(window, hwnd):
    """Rounded corners and no window border; the see-through comes from WIN_OPACITY."""
    from System.Drawing import Color
    on_ui_thread(window, lambda: setattr(window.native.browser.webview, "DefaultBackgroundColor", Color.Transparent))

    dwm = ctypes.windll.dwmapi
    dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(_Margins(-1, -1, -1, -1)))  # see-through under the whole window
    # dark mode, round corners, no window border (DWMWA_COLOR_NONE), no blur backdrop (crisper on dark backgrounds)
    for attr, value in ((20, 1), (33, 2), (34, 0xFFFFFFFE), (38, 1)):
        v = ctypes.c_uint(value)
        dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), 4)


def keep_glass_lit(hwnd):
    # Windows draws inactive windows differently (e.g. when the box opened without getting focus);
    # WM_NCACTIVATE(TRUE) makes it draw the box as active anyway
    user32.SendMessageW(hwnd, 0x86, 1, 0)


def fade(window, start, end, steps=8):
    """Fades the whole window (glass included) on Windows; about 150ms."""
    for i in range(1, steps + 1):
        on_ui_thread(window, lambda o=start + (end - start) * i / steps: setattr(window.native, "Opacity", o))
        time.sleep(0.018)


def is_open(window):
    if MAC:
        return bool(window.native and window.native.isVisible())
    hwnd = user32.FindWindowW(None, "quickcord")
    return bool(hwnd and user32.IsWindowVisible(hwnd))


def hovered_unfocused(window):
    """The box is open with the mouse over it, but another app has the keyboard."""
    if MAC:
        w = window.native  # NSWindow
        return bool(is_open(window) and not AppKit.NSApplication.sharedApplication().isActive()
                    and AppKit.NSPointInRect(AppKit.NSEvent.mouseLocation(), w.frame()))
    hwnd = user32.FindWindowW(None, "quickcord")
    if not is_open(window) or user32.GetForegroundWindow() == hwnd:
        return False
    pt, rect = wintypes.POINT(), wintypes.RECT()
    user32.GetCursorPos(ctypes.byref(pt))
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left <= pt.x < rect.right and rect.top <= pt.y < rect.bottom


def activate_mac():
    # AppKit calls must run on the main thread, which pywebview's run loop owns
    AppHelper.callAfter(AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_, True)


# quickcord.app's launcher sets this to its own path (see mac/launcher.m); unset when run from a terminal
APP_LAUNCHER = os.environ.get("QUICKCORD_APP") if MAC else None
ASKED_LOGIN_ITEM = os.path.expanduser("~/Library/Application Support/quickcord/asked-login-item")

INPUT_MONITORING_HELP = (
    "quickcord can't see the keyboard yet, so double-tapping Option won't work. Open System Settings > "
    "Privacy & Security > Input Monitoring and turn on "
    + ("quickcord. It starts working as soon as you do." if APP_LAUNCHER else
       "the app you ran quickcord from (Terminal, iTerm, your editor), then quit and restart quickcord."))
INPUT_MONITORING_PANE = "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"


def keyboard_blocked(listener):
    """macOS silently hands a keyboard listener no events until the app is granted Input Monitoring."""
    listener.wait()
    return not listener.is_alive() or not Quartz.CGPreflightListenEventAccess()


def restart_when_allowed(busy):
    """A keyboard tap only works in a process started after the permission was granted, so start over then."""
    # CGPreflightListenEventAccess keeps its first answer for the life of a process, so ask a fresh one each time
    check = [sys.executable, "-c", "import sys, Quartz; sys.exit(not Quartz.CGPreflightListenEventAccess())"]
    while subprocess.run(check).returncode:
        time.sleep(2)
    busy.acquire()  # not in the middle of logging in
    os.execv(sys.executable, [sys.executable, *sys.argv])


def login_item(action):
    """Open at Login, via the app's launcher since macOS ties it to the app bundle: status, enable or disable.
    Returns whether it's now on."""
    if action != "status":
        subprocess.run([APP_LAUNCHER, "--login-item", action], capture_output=True, timeout=10)
    # whatever enable/disable reported, ask macOS what actually happened
    r = subprocess.run([APP_LAUNCHER, "--login-item", "status"], capture_output=True, text=True, timeout=10)
    return r.stdout.strip() == "enabled"


def ask(title, text, yes, no):
    """A native yes/no alert; call from any thread except the main one."""
    done, answer = threading.Event(), []

    def run():
        app = AppKit.NSApplication.sharedApplication()
        app.activateIgnoringOtherApps_(True)
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(text)
        alert.addButtonWithTitle_(yes)
        alert.addButtonWithTitle_(no)
        if APP_LAUNCHER:
            alert.setIcon_(app_icon())
        answer.append(alert.runModal() == AppKit.NSAlertFirstButtonReturn)
        done.set()

    AppHelper.callAfter(run)
    done.wait()
    return answer[0]


def app_icon():
    bundle = os.path.dirname(os.path.dirname(os.path.dirname(APP_LAUNCHER)))  # .app/Contents/MacOS/quickcord
    return AppKit.NSWorkspace.sharedWorkspace().iconForFile_(bundle)


def offer_login_item():
    """Once, after you're signed in: ask whether quickcord should open at login."""
    if not APP_LAUNCHER or os.path.exists(ASKED_LOGIN_ITEM) or not load_token():
        return False
    os.makedirs(os.path.dirname(ASKED_LOGIN_ITEM), exist_ok=True)
    open(ASKED_LOGIN_ITEM, "w").close()
    if login_item("status") or not ask(
            "Open quickcord when you log in?",
            "Then double-tapping Option is always ready. You can change this later from quickcord's menu bar icon.",
            "Open at Login", "Not Now"):
        return False
    return login_item("enable")


def main():
    api = Api()
    # inline html, not a file path: a path makes pywebview serve this whole folder on localhost
    with open(os.path.join(HERE, "ui.html"), encoding="utf-8") as f:
        html = f.read().replace("<html>", f'<html class="{"mac" if MAC else "win"}">', 1)
    # macOS: transparent window, ui.html draws and animates the panel itself.
    # Windows: not pywebview's transparent mode (it force-shows the window on load); glass() makes it see-through
    window = webview.create_window("quickcord", html=html, js_api=api, width=WIDTH, height=HEIGHT, min_size=(200, 40),
                                   frameless=True, on_top=True, hidden=True, transparent=MAC, background_color="#000000")
    api._window = window
    notice = []  # set when the hotkey can't work, shown every time the box opens

    def show():
        if is_open(window):  # already up (e.g. Open from the menu): leave it and what you've typed alone
            return
        screen = webview.screens[0]
        if not MAC:
            on_ui_thread(window, lambda: setattr(window.native, "Opacity", 0.0))
        window.resize(WIDTH, HEIGHT)
        window.move((screen.width - WIDTH) // 2, screen.height // 4)
        window.show()
        if MAC:
            activate_mac()  # pywebview's show() makes the window key; this makes the app frontmost
        else:
            hwnd = user32.FindWindowW(None, "quickcord")
            if hwnd:
                glass(window, hwnd)
                if user32.GetForegroundWindow() != hwnd:
                    force_foreground(hwnd)
                keep_glass_lit(hwnd)
                # pywebview only focuses the page on the very first show; typing needs it every time
                on_ui_thread(window, lambda: window.native.browser.webview.Focus())
        window.evaluate_js(f"onShow({json.dumps(notice[0] if notice else None)})")
        if not MAC:
            fade(window, 0, WIN_OPACITY)

    def show_soon():
        # off the calling thread: on macOS menu callbacks run on the main thread, where evaluate_js would deadlock
        threading.Thread(target=show, daemon=True).start()

    logging_in = threading.Lock()  # held while the login window is open, so a restart doesn't lose it

    logged_in = [bool(load_token())]  # cached for the menu, which is rebuilt on the main thread

    def refresh_menu():
        logged_in[0] = bool(load_token())
        if MAC:
            AppHelper.callAfter(icon.update_menu)  # AppKit only on the main thread
        else:
            icon.update_menu()

    def login_once():
        if logging_in.acquire(blocking=False):
            try:
                login()
            finally:
                logging_in.release()
                refresh_menu()

    def log_in_or_out():
        if logged_in[0]:
            # only forgets the token saved here; Discord's own session list still shows it until it expires
            delete_token()
            refresh_menu()
        else:
            threading.Thread(target=login_once, daemon=True).start()

    at_login = [bool(APP_LAUNCHER) and login_item("status")]

    def toggle_login_item(icon):
        at_login[0] = login_item("disable" if at_login[0] else "enable")
        icon.update_menu()

    def quit_app(icon):
        icon.visible = False
        if MAC:
            AppKit.NSApplication.sharedApplication().terminate_(None)
        else:
            icon.stop()
            window.destroy()

    # shortcut: theme is read once at startup, so switching light/dark needs a restart to swap the icon.
    # macOS doesn't need it: the black icon becomes a template image below, which the menu bar tints itself.
    img = Image.open(os.path.join(HERE, "light-icon.png" if MAC or light_theme() else "icon.png")).resize(
        (64, 64), Image.LANCZOS)
    icon = pystray.Icon("quickcord", img, f"quickcord (double-tap {'Option' if MAC else 'Alt'})", pystray.Menu(
        pystray.MenuItem("Open", lambda: show_soon(), default=True),
        pystray.MenuItem(lambda _: "Log out" if logged_in[0] else "Log in", lambda: log_in_or_out()),
        *([pystray.MenuItem("Open at Login", toggle_login_item, checked=lambda _: at_login[0])] if APP_LAUNCHER else []),
        pystray.MenuItem("Quit", quit_app),
    ))

    if MAC:
        # a menu bar app: no Dock icon or app menu. pywebview's Cocoa backend sets the regular policy when it's
        # imported, which start() would otherwise do after us, so import it first.
        importlib.import_module("webview.platforms.cocoa")
        AppKit.NSApplication.sharedApplication().setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        # pywebview's start() owns the main thread and its run loop. pystray's macOS backend only needs that
        # run loop, so set the status item up here on the main thread instead of in a background setup thread.
        icon.run_detached(lambda _: None)
        icon.visible = True
        icon._status_item.button().setImage_(menu_bar_image())  # pystray has no option for template images

    def started():
        detector = DoubleTap()

        def close_soon():  # off the key hook's thread: blocking there would stall every keypress
            threading.Thread(target=lambda: window.evaluate_js("closeBox()"), daemon=True).start()

        def toggle():  # the hotkey toggles: closing keeps what you've typed for next time, like Esc
            close_soon() if is_open(window) else show_soon()

        def on(pressed):
            def handler(k):  # must return None: pynput stops the listener if a callback returns False
                if detector.feed(pressed, k in ALTS, time.monotonic()):
                    toggle()
                # Esc while just hovering the box (it isn't focused, so the page never sees the key)
                if MAC and pressed and k == keyboard.Key.esc and hovered_unfocused(window):
                    close_soon()
            return handler

        swallowed = []  # an Esc press we swallowed, so its release gets swallowed too
        lone_alt = [False]  # Alt is down and no other key has been pressed since

        def win32_filter(msg, data):
            down = msg in (0x100, 0x104)  # WM_KEYDOWN, WM_SYSKEYDOWN
            if data.vkCode in (0x12, 0xA4, 0xA5):  # Alt, left Alt, right Alt
                if data.flags & 0x10:  # injected by us (focus trick, menu mask): never one of your taps
                    return False
                if down:
                    lone_alt[0] = True
                elif lone_alt[0] and is_open(window) and user32.GetForegroundWindow() == user32.FindWindowW(None, "quickcord"):
                    # a lone Alt release would put the focused box in menu mode, which blurs and closes it.
                    # Swallow it and replay it behind an unassigned key, so it's an Alt+key combo instead.
                    lone_alt[0] = False
                    if detector.feed(False, True, time.monotonic()):
                        toggle()
                    user32.keybd_event(0xE8, 0, 0, 0)
                    user32.keybd_event(0xE8, 0, 2, 0)
                    # the real key-up, so Alt isn't left held down (right Alt is an extended key)
                    user32.keybd_event(data.vkCode, 0, 2 | (1 if data.vkCode == 0xA5 else 0), 0)
                    listener.suppress_event()
                return True
            if down:
                lone_alt[0] = False
            # same hover Esc as macOS, but swallowed so it doesn't also hit the app underneath
            if data.vkCode != 0x1B:  # VK_ESCAPE
                return True
            if down:
                if hovered_unfocused(window):
                    swallowed.append(True)
                    close_soon()
                    listener.suppress_event()
            elif swallowed:
                swallowed.clear()
                listener.suppress_event()
            return True

        listener = keyboard.Listener(on_press=on(True), on_release=on(False), daemon=True,
                                     win32_event_filter=win32_filter)
        listener.start()

        if MAC and keyboard_blocked(listener):
            Quartz.CGRequestListenEventAccess()  # adds quickcord to the Input Monitoring list, switched off
            notice.append(INPUT_MONITORING_HELP)  # for whenever the box is opened from the menu bar meanwhile
            # an alert rather than the box: it stays put while you go to System Settings
            if ask("quickcord needs to see the keyboard", INPUT_MONITORING_HELP, "Open System Settings", "Later"):
                AppKit.NSWorkspace.sharedWorkspace().openURL_(AppKit.NSURL.URLWithString_(INPUT_MONITORING_PANE))
            if APP_LAUNCHER:
                restart_when_allowed(logging_in)  # logging in waits for the restarted, working process
        if not MAC:
            icon.run_detached()

        if not load_token():
            login_once()
        if MAC and offer_login_item():
            at_login[0] = True
            AppHelper.callAfter(icon.update_menu)

    webview.start(started)


if __name__ == "__main__":
    main()
