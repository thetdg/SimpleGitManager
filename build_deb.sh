#!/usr/bin/env bash
#
# Builds git-helper_<version>_<arch>.deb using PyInstaller.
#
# Usage:  ./build_deb.sh [version]        (default version: 1.0.0)
#         MAINTAINER="Name <mail@example.com>" ./build_deb.sh 1.2.0
#
# IMPORTANT: build on Ubuntu 22.04. A PyInstaller bundle runs on any system whose
# glibc is the same or newer than the build machine's, so a 22.04 build installs
# on 22.04 and every later release.
#
set -euo pipefail

APP="git-helper"
TITLE="Barsha's Git Helper"
VERSION="${1:-1.0.0}"
MAINTAINER="${MAINTAINER:-Git Helper Maintainer <thetdg@live.com>}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="$ROOT/build_deb"
VENV="$BUILD/venv"
PKG="$BUILD/pkg"
ARCH="$(dpkg --print-architecture)"
OUT="$ROOT/${APP}_${VERSION}_${ARCH}.deb"

[ -f "$ROOT/git_helper.py" ]     || { echo "git_helper.py not found next to this script."; exit 1; }
[ -f "$ROOT/assets/icon.png" ]   || { echo "assets/icon.png not found."; exit 1; }

missing=()
command -v python3   >/dev/null || missing+=(python3)
command -v dpkg-deb  >/dev/null || missing+=(dpkg-dev)
command -v objdump   >/dev/null || missing+=(binutils)
python3 -c "import venv, ensurepip" 2>/dev/null || missing+=(python3-venv)
if [ "${#missing[@]}" -gt 0 ]; then
    echo "Missing build tools. Install them with:"
    echo "  sudo apt install python3 python3-venv python3-pip binutils dpkg-dev"
    exit 1
fi

echo "==> Preparing build environment"
rm -rf "$BUILD/dist" "$BUILD/work" "$PKG"
mkdir -p "$BUILD"
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet "PyQt6>=6.5" pyinstaller

echo "==> Running PyInstaller"
"$VENV/bin/pyinstaller" \
    --noconfirm --clean --onedir --windowed \
    --name "$APP" \
    --distpath "$BUILD/dist" --workpath "$BUILD/work" --specpath "$BUILD" \
    --add-data "$ROOT/assets/icon.png:assets" \
    --exclude-module tkinter \
    "$ROOT/git_helper.py"

echo "==> Staging package"
mkdir -p "$PKG/DEBIAN" \
         "$PKG/opt/$APP" \
         "$PKG/usr/bin" \
         "$PKG/usr/share/applications" \
         "$PKG/usr/share/doc/$APP"
cp -a "$BUILD/dist/$APP/." "$PKG/opt/$APP/"
ln -s "/opt/$APP/$APP" "$PKG/usr/bin/$APP"

# Icons at several sizes (resized with Qt, no extra tools needed)
QT_QPA_PLATFORM=offscreen "$VENV/bin/python" - "$ROOT/assets/icon.png" "$PKG" "$APP" <<'PY'
import os, sys
from PyQt6.QtGui import QImage
from PyQt6.QtCore import Qt
src, pkg, app = sys.argv[1:4]
img = QImage(src)
if img.isNull():
    sys.exit("Could not read " + src)
for size in (48, 128, 256):
    d = os.path.join(pkg, "usr/share/icons/hicolor/%dx%d/apps" % (size, size))
    os.makedirs(d, exist_ok=True)
    scaled = img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
    scaled.save(os.path.join(d, app + ".png"))
PY

cat > "$PKG/usr/share/applications/$APP.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$TITLE
Comment=Simple Git tasks without the command line
Exec=/usr/bin/$APP
Icon=$APP
Terminal=false
Categories=Development;Utility;
StartupWMClass=$APP
StartupNotify=true
EOF

cat > "$PKG/usr/share/doc/$APP/copyright" <<EOF
$TITLE - all rights reserved by the package maintainer.
Bundles Python, Qt and PyQt6, which are distributed under their own licenses.
EOF

cat > "$PKG/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache  >/dev/null 2>&1 && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
exit 0
EOF
cp "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/postrm"
chmod 755 "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/postrm"

SIZE_KB="$(du -sk "$PKG/opt" "$PKG/usr" | awk '{s+=$1} END {print s}')"
cat > "$PKG/DEBIAN/control" <<EOF
Package: $APP
Version: $VERSION
Section: vcs
Priority: optional
Architecture: $ARCH
Maintainer: $MAINTAINER
Installed-Size: $SIZE_KB
Depends: git, openssh-client, libc6 (>= 2.35), libxcb-cursor0, libxkbcommon-x11-0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-shape0, libxcb-xinerama0, libxcb-xkb1, libegl1, libgl1, libfontconfig1, libdbus-1-3, libglib2.0-0
Description: Simple Git tasks for everyone
 $TITLE lets non-technical users fetch, pull, add, commit, push and stash
 changes in a Git project using plain language and big buttons.
EOF

chmod -R u+rwX,go+rX,go-w "$PKG"

echo "==> Building .deb"
rm -f "$OUT"
dpkg-deb --root-owner-group -Zxz --build "$PKG" "$OUT"

echo
echo "Done: $OUT"
echo "Install with:  sudo apt install ./$(basename "$OUT")"
