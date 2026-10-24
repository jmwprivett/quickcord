# quickcord

Double-tap **Alt** anywhere on Windows to pop up a small box and send a Discord DM without switching to the app.

- The dropdown on the right lists your DMs and group DMs, most recent first, with the newest one already picked.
- **Enter** sends, **Shift+Enter** adds a new line, **Tab** opens the dropdown (type to filter, arrows + Enter to pick), **Esc** closes.
- Messages go out as you, through Discord's API, using your account token.

> Automating a user account is against Discord's Terms of Service and can get the account banned. Use at your own risk.

## Setup

```
pip install pynput pystray pillow pywebview
```

The first time you run it, a Discord login window opens. Log in like normal; quickcord saves your token to `token.txt` (gitignored, never share it) and closes the window. If you ever get logged out, right-click the tray icon and pick **Log in**.

## Run

```
pythonw quicksend.pyw
```

A blurple dot appears in the system tray while it's running. Right-click it and pick **Quit** to close it. To start it with Windows, put a shortcut to `quicksend.pyw` in `shell:startup`.

Test: `python test_quicksend.py`
