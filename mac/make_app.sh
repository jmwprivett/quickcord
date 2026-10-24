#!/bin/sh
# Builds quickcord.app (default: ~/Applications/quickcord.app) that runs this checkout of quickcord.
# Usage: mac/make_app.sh [destination folder]
set -eu

REPO=$(cd "$(dirname "$0")/.." && pwd)
DEST=${1:-"$HOME/Applications"}
APP="$DEST/quickcord.app"
BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT

if [ ! -x "$REPO/.venv/bin/python" ]; then
    echo "Creating $REPO/.venv"
    python3 -m venv "$REPO/.venv"
fi
"$REPO/.venv/bin/pip" install -q pynput pystray pillow pywebview keyring

# app icon: the logo in white on a Discord-blurple rounded square
mkdir "$BUILD/quickcord.iconset"
"$REPO/.venv/bin/python" - "$REPO/icon.png" "$BUILD/quickcord.iconset" <<'EOF'
import sys
from PIL import Image, ImageDraw
logo, out = sys.argv[1], sys.argv[2]
icon = Image.new("RGBA", (1024, 1024))
ImageDraw.Draw(icon).rounded_rectangle((100, 100, 924, 924), radius=185, fill="#5865f2")
mark = Image.open(logo).convert("RGBA")
mark = mark.crop(mark.getchannel("A").getbbox())  # the logo isn't centred in its PNG
scale = 600 / max(mark.size)
mark = mark.resize((round(mark.width * scale), round(mark.height * scale)), Image.LANCZOS)
white = Image.new("RGBA", mark.size, "white")
white.putalpha(mark.getchannel("A"))
icon.alpha_composite(white, ((1024 - mark.width) // 2, (1024 - mark.height) // 2))
for size in (16, 32, 128, 256, 512):
    icon.resize((size, size), Image.LANCZOS).save(f"{out}/icon_{size}x{size}.png")
    icon.resize((size * 2, size * 2), Image.LANCZOS).save(f"{out}/icon_{size}x{size}@2x.png")
EOF

mkdir -p "$BUILD/quickcord.app/Contents/MacOS" "$BUILD/quickcord.app/Contents/Resources"
iconutil -c icns "$BUILD/quickcord.iconset" -o "$BUILD/quickcord.app/Contents/Resources/quickcord.icns"
xcrun clang -fobjc-arc -O2 -mmacosx-version-min=13.0 -framework Foundation -framework ServiceManagement \
    "$REPO/mac/launcher.m" -o "$BUILD/quickcord.app/Contents/MacOS/quickcord"

cat > "$BUILD/quickcord.app/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>quickcord</string>
    <key>CFBundleDisplayName</key><string>quickcord</string>
    <key>CFBundleIdentifier</key><string>com.jmwprivett.quickcord</string>
    <key>CFBundleExecutable</key><string>quickcord</string>
    <key>CFBundleIconFile</key><string>quickcord</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>1.0</string>
    <key>CFBundleVersion</key><string>1</string>
    <key>LSMinimumSystemVersion</key><string>13.0</string>
    <key>LSUIElement</key><true/>
    <key>QuickcordDir</key><string>$REPO</string>
</dict>
</plist>
EOF

# ad-hoc signature: gives the app a stable identity for its privacy permissions and login item
codesign --force --sign - "$BUILD/quickcord.app"

mkdir -p "$DEST"
rm -rf "$APP"
mv "$BUILD/quickcord.app" "$APP"
echo "Built $APP"
