import importlib.machinery
import importlib.util

# .pyw is only a known source suffix on Windows, so name the loader explicitly
spec = importlib.util.spec_from_file_location("qs", "quicksend.pyw",
                                              loader=importlib.machinery.SourceFileLoader("qs", "quicksend.pyw"))
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

# token storage round-trips without plaintext on disk, and bad input is rejected before hitting the API
import os, tempfile, uuid
if qs.MAC:
    # throwaway Keychain item, so the real "quickcord" token is never touched
    import keyring.errors
    qs.KEYCHAIN_SERVICE = "quickcord-test-" + uuid.uuid4().hex
    try:
        assert qs.load_token() is None
        qs.save_token("abc.def-ghi")
        assert qs.load_token() == "abc.def-ghi"
        qs.save_token("second")  # overwrites rather than adding a second item
        assert qs.load_token() == "second"
        qs.delete_token()
        assert qs.load_token() is None
        qs.delete_token()  # logging out twice is fine
    finally:
        try:
            qs._keychain().delete_password(qs.KEYCHAIN_SERVICE, qs.KEYCHAIN_ACCOUNT)
        except keyring.errors.PasswordDeleteError:
            pass
    assert qs.load_token() is None
else:
    qs.TOKEN_FILE = os.path.join(tempfile.mkdtemp(), "token.dat")
    assert qs.load_token() is None
    qs.save_token("abc.def-ghi")
    assert b"abc" not in open(qs.TOKEN_FILE, "rb").read()
    assert qs.load_token() == "abc.def-ghi"
    open(qs.TOKEN_FILE, "wb").write(b"garbage")
    assert qs.load_token() is None
    qs.delete_token()
    assert not os.path.exists(qs.TOKEN_FILE)
    qs.delete_token()  # logging out twice is fine

    # Open at Login, under a throwaway Run value so the real "quickcord" entry is never touched
    qs.RUN_VALUE = "quickcord-test-" + uuid.uuid4().hex
    try:
        assert qs.login_item("status") is False
        assert qs.login_item("enable") is True
        assert qs.login_item("status") is True
    finally:
        assert qs.login_item("disable") is False
    assert qs.login_item("disable") is False  # turning it off twice is fine
assert qs.Api().send("../users/@me", "hi") == {"error": "Pick a conversation"}
assert qs.Api().send("123", "x" * 2001)["error"]
print("ok")
