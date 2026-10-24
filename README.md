# quickcord

Double-tap **Alt** (Windows) or **Option** (macOS) anywhere to pop up a small box and send a Discord DM without switching to the app.

- The dropdown on the right lists your DMs and group DMs, most recent first, with the newest one already picked.
- **Enter** sends, **Shift+Enter** adds a new line, **Tab** opens the dropdown (type to filter, arrows + Enter to pick), **Esc** or the same double-tap closes it.
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

A white Discord logo appears in the system tray while it's running. Right-click it for **Open**, **Log in**/**Log out**, **Open at Login** (start quickcord when you sign in to Windows) and **Quit**.

## macOS

### Setup

```
mac/make_app.sh
```

That sets up `.venv` with the packages quickcord needs (pynput, pystray, pillow, pywebview, keyring), and builds **quickcord.app** in `~/Applications`. The app runs this folder's code, so after a `git pull` there's nothing to rebuild; run the script again only if you move the folder or `mac/launcher.m` changes.

### Run

Open **quickcord** from Spotlight, Launchpad or `~/Applications`. On the first run:

1. **Keyboard permission.** quickcord asks for **Input Monitoring** so it can notice the Option double-tap. Click **Open System Settings** and turn on **quickcord**. It restarts itself and carries on as soon as you do.
2. **Discord login.** A Discord login window opens. Log in like normal; quickcord saves your token in your login **Keychain** (item "quickcord"), never in a file, and closes the window.
3. **Open at Login?** quickcord asks once whether to start when you log in to your Mac. Change it any time with **Open at Login** in its menu.

There's no Dock icon. A Discord logo appears in the menu bar while it's running (macOS tints it to match light, dark or wallpaper-coloured menu bars); click it for **Open**, **Log in**, **Open at Login** and **Quit**.

### From a terminal

`.venv/bin/python quicksend.pyw` works too, but then macOS asks for Input Monitoring for the terminal app instead of quickcord, and you need to restart quickcord after allowing it. The Open at Login option only exists in the app.

## Test

```
python test_quicksend.py
```

On macOS the token test round-trips a throwaway Keychain item and deletes it afterwards.

Tray icon: [Discord icon by Icons8](https://icons8.com).
