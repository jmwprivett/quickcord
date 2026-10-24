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

Put your Discord token in `token.txt` next to `quicksend.pyw` (it's gitignored, never share it). To find it: open discord.com in a browser, press F12, go to the Network tab, click any request to `discord.com/api`, and copy the `Authorization` request header.

## Run

```
pythonw quicksend.pyw
```

A blurple dot appears in the system tray while it's running. Right-click it and pick **Quit** to close it. To start it with Windows, put a shortcut to `quicksend.pyw` in `shell:startup`.

Test: `python test_quicksend.py`
