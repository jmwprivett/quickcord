import importlib.util

spec = importlib.util.spec_from_file_location("qs", "quicksend.pyw")
qs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qs)


def taps(*events):
    d = qs.DoubleTap()
    return [d.feed(p, a, t) for p, a, t in events]


# clean double tap fires on second release
assert taps((1, 1, 0), (0, 1, .05), (1, 1, .15), (0, 1, .2))[-1] is True
# too slow
assert taps((1, 1, 0), (0, 1, .05), (1, 1, .6), (0, 1, .65))[-1] is False
# Alt+Tab in between doesn't count
assert taps((1, 1, 0), (1, 0, .02), (0, 1, .05), (1, 1, .15), (0, 1, .2))[-1] is False
# key-repeat while holding Alt is one tap, and a held Alt+key isn't a tap
assert taps((1, 1, 0), (1, 1, .03), (0, 1, .05), (1, 1, .1), (0, 1, .15))[-1] is True
# triple tap fires once, not twice
assert taps((1, 1, 0), (0, 1, .05), (1, 1, .1), (0, 1, .15), (1, 1, .2), (0, 1, .25)) == [False, False, False, True, False, False]

# DMs and groups sorted newest first; servers, empty DMs and missing avatars handled
chats = qs.recent_chats([
    {"id": "1", "type": 1, "last_message_id": "100", "recipients": [{"id": "9", "username": "old", "avatar": None}]},
    {"id": "2", "type": 1, "last_message_id": "300", "recipients": [{"id": "8", "username": "u", "global_name": "New", "avatar": "abc"}]},
    {"id": "3", "type": 3, "last_message_id": "200", "name": None, "icon": None,
     "recipients": [{"id": "7", "username": "a"}, {"id": "6", "username": "b"}]},
    {"id": "4", "type": 1, "last_message_id": None, "recipients": [{"id": "5", "username": "never"}]},
    {"id": "5", "type": 0},
])
assert [c["name"] for c in chats] == ["New", "a, b", "old", "never"], chats
assert chats[0]["avatar"].endswith("/avatars/8/abc.png?size=64")
print("ok")
