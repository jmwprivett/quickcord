# quickcord

Double-tap **Alt** anywhere on Windows to pop up a small box and send a Discord message without switching to the app.

- Type your message on the left and who it goes to on the right (a friend, channel or server name, same as Discord's Ctrl+K search). Leave "to" empty to send to the currently open chat.
- **Enter** sends, **Shift+Enter** adds a new line, **Esc** closes.
- It drives the running Discord desktop app, so messages go out as you, with no bot or token. Discord must be running (tray is fine).

## Run

```
pip install pynput pystray pillow
pythonw quicksend.pyw
```

A blurple dot appears in the system tray while it's running. Right-click it and pick **Quit** to close it.

To start it with Windows, put a shortcut to `quicksend.pyw` in `shell:startup`.

Test: `python test_quicksend.py`
