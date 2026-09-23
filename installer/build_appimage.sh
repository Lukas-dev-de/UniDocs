#!/usr/bin/env bash
#
# Wrap a `flet build linux` bundle into a single-file AppImage.
#
#   ./build_appimage.sh build/linux dist/UniDocs-linux-x86_64.AppImage
#
# The release workflow calls this; run it locally for a one-off build. The
# bundle keeps the layout flet produced (launcher plus data/, lib/,
# python3.12/ and site-packages/ inside usr/bin), so the launcher still finds
# its data folder next to itself, exactly like in a normal install.
#
# GTK 3 is expected on the machine, not bundled - same as the plain folder
# build, see the README.

set -euo pipefail

BUNDLE="${1:?usage: build_appimage.sh <flet-bundle-dir> <output.AppImage>}"
OUTPUT="${2:?usage: build_appimage.sh <flet-bundle-dir> <output.AppImage>}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ICON="$HERE/icon.png"

[ -d "$BUNDLE" ] || { printf 'error: no such folder: %s\n' "$BUNDLE" >&2; exit 1; }
[ -f "$BUNDLE/unidocs" ] || { printf 'error: %s is not a UniDocs bundle\n' "$BUNDLE" >&2; exit 1; }
[ -f "$ICON" ] || { printf 'error: icon missing: %s\n' "$ICON" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

appdir="$work/unidocs.AppDir"
mkdir -p "$appdir/usr/bin"
cp -a "$BUNDLE/." "$appdir/usr/bin/"

cp "$ICON" "$appdir/unidocs.png"
ln -sf unidocs.png "$appdir/.DirIcon"

cat > "$appdir/unidocs.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=UniDocs
Comment=Documents, modules and tags
Exec=unidocs
Icon=unidocs
Terminal=false
Categories=Office;Utility;
EOF

cat > "$appdir/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
cd "$HERE/usr/bin" 2>/dev/null || true
exec "$HERE/usr/bin/unidocs" "$@"
EOF
chmod +x "$appdir/AppRun"

mkdir -p "$(dirname "$OUTPUT")"

# appimagetool is itself an AppImage; --appimage-extract-and-run skips the FUSE
# mount that CI runners and minimal machines cannot do. If this URL ever 404s,
# the tool moved back to AppImage/AppImageKit.
tool="$work/appimagetool"
printf 'Downloading appimagetool\n'
if command -v curl >/dev/null 2>&1; then
    curl -fsSL -o "$tool" \
        https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
else
    wget -q -O "$tool" \
        https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
fi
chmod +x "$tool"

ARCH=x86_64 "$tool" --appimage-extract-and-run "$appdir" "$OUTPUT"
printf 'Wrote %s\n' "$OUTPUT"
