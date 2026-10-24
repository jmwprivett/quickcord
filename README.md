# quickcord

Double-tap **Alt** (Windows) or **Option** (macOS) anywhere to pop up a small box and send a Discord DM without switching to the app.

- The dropdown on the right lists your DMs and group DMs, most recent first, with the newest one already picked.
- **Enter** sends, **Shift+Enter** adds a new line, **Tab** opens the dropdown (type to filter, arrows + Enter to pick), **Esc** closes.
- Messages go out as you, through Discord's API, using your account token.

> Automating a user account is against Discord's Terms of Service and can get the account banned. Use at your own risk.

## Windows

### Setup

```
pip install pynput pystray pillow pywebview
```

The first time you run it, a Discord login window opens. Log in like normal; quickcord saves your token to `%APPDATA%\quickcord\token.dat`, encrypted so only your Windows account on this PC can read it, and closes the window. If you ever get logged out, right-click the tray icon and pick **Log in**.

### Run

```
pythonw quicksend.pyw
```

A blurple dot appears in the system tray while it's running. Right-click it and pick **Quit** to close it. To start it with Windows, put a shortcut to `quicksend.pyw` in `shell:startup`.

## macOS

### Setup

```
python3 -m venv .venv
.venv/bin/pip install pynput pystray pillow pywebview keyring
```

(pywebview pulls in the pyobjc packages quickcord uses for the window, Keychain and menu bar.)

The first time you run it, a Discord login window opens. Log in like normal; quickcord saves your token in your login **Keychain** (item "quickcord"), never in a file, and closes the window. If you ever get logged out, click the blurple dot in the menu bar and pick **Log in**.

### Permissions

macOS only lets an app see global key presses after you allow it. Open **System Settings > Privacy & Security** and turn on the app you start quickcord from (Terminal, iTerm, your editor, or the quickcord login item below) under both:

- **Input Monitoring**: needed to notice the Option double-tap
- **Accessibility**: pynput asks for it too

Then quit and restart quickcord. If the permission is missing, quickcord says so in its box at startup, and again whenever you open the box from the menu bar, instead of silently ignoring the hotkey.

### Run

```
.venv/bin/python quicksend.pyw
```

There's no Dock icon. A blurple dot appears in the menu bar while it's running; click it for **Open**, **Log in** and **Quit**.

### Start at login

1. Open **Script Editor**, paste this (fix the path), and save it as an **Application** called `quickcord`:
   ```applescript
   do shell script "cd ~/dev/quickcord && .venv/bin/python quicksend.pyw > /dev/null 2>&1 &"
   ```
2. Add that app in **System Settings > General > Login Items & Extensions > Open at Login**.
3. Run it once and grant it **Input Monitoring** and **Accessibility** as above. Permissions belong to the app that launched quickcord, so the login item needs its own grants even if Terminal already has them.

## Test

```
python test_quicksend.py
```

On macOS the token test round-trips a throwaway Keychain item and deletes it afterwards.
