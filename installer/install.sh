#!/usr/bin/env bash
#
# UniDocs installer for Linux.
#
# Installs UniDocs for the current user only - no root, nothing outside $HOME:
#
#   ~/.local/share/unidocs                                  the app itself
#   ~/.local/bin/unidocs                                     symlink to the launcher
#   ~/.local/share/applications/unidocs.desktop              menu entry
#   ~/.local/share/icons/hicolor/512x512/apps/unidocs.png    icon
#
# Usage:
#   ./install.sh                                install / update to the newest release
#   ./install.sh v2.4.0                         install a specific tag
#   ./install.sh ./UniDocs-linux-x86_64.tar.gz  install from a local file
#   ./install.sh --uninstall                    remove the install (documents stay)
#
# Running it again is how you update by hand. The app also updates itself:
# "Install now" in the update dialog, and patch releases install on startup.
#
# Requires GTK3, which every normal desktop already has. It is deliberately not
# bundled, see the README.

set -euo pipefail

REPO="Lukas-dev-de/UniDocs"
APP="unidocs"
ASSET="UniDocs-linux-x86_64.tar.gz"

INSTALL_DIR="${UNIDOCS_DIR:-$HOME/.local/share/unidocs}"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APPS_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/512x512/apps"

die() { printf 'error: %s\n' "$1" >&2; exit 1; }
info() { printf '  %s\n' "$1"; }

if [ "${1:-}" = "-u" ] || [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$INSTALL_DIR" "$APPS_DIR/unidocs.desktop" "$BIN_DIR/$APP"
    # every hicolor size, not just the one we install today: older releases put
    # the icon elsewhere, and a leftover there keeps showing the old logo
    rm -f "$DATA_HOME"/icons/hicolor/*/apps/unidocs.png
    printf 'UniDocs removed. Your documents are untouched.\n'
    exit 0
fi

download() {   # download <url> <destination>
    if command -v curl >/dev/null 2>&1; then
        curl -fSL --retry 3 -o "$2" "$1"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$2" "$1"
    else
        die "neither curl nor wget found"
    fi
}

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

archive=""
case "${1:-latest}" in
    ""|latest) url="https://github.com/${REPO}/releases/latest/download/${ASSET}" ;;
    *.tar.gz)  [ -f "$1" ] || die "no such file: $1"; archive="$1" ;;
    *)         url="https://github.com/${REPO}/releases/download/${1}/${ASSET}" ;;
esac

if [ -z "$archive" ]; then
    printf 'Downloading %s\n' "$url"
    archive="$scratch/$ASSET"
    download "$url" "$archive" || die "download failed: $url"
fi

printf 'Installing to %s\n' "$INSTALL_DIR"
staging="$scratch/unpacked"
mkdir -p "$staging"
tar -xzf "$archive" -C "$staging" || die "not a UniDocs archive: $archive"
[ -f "$staging/$APP" ] || die "the archive has no '$APP' launcher"
chmod +x "$staging/$APP"

# swap the folder, so an interrupted install never leaves a broken app behind
mkdir -p "$(dirname "$INSTALL_DIR")"
rm -rf "$INSTALL_DIR.new" "$INSTALL_DIR.old"
mv "$staging" "$INSTALL_DIR.new"
if [ -e "$INSTALL_DIR" ]; then mv "$INSTALL_DIR" "$INSTALL_DIR.old"; fi
mv "$INSTALL_DIR.new" "$INSTALL_DIR"
rm -rf "$INSTALL_DIR.old"

# launcher on PATH
mkdir -p "$BIN_DIR"
ln -sfn "$INSTALL_DIR/$APP" "$BIN_DIR/$APP"

# icon + menu entry
# Drop any icon left in another hicolor size first. Older releases installed the
# 256x256 copy and a later one switched to 512x512; the desktop then picks
# whichever size fits and would keep rendering the stale logo.
rm -f "$DATA_HOME"/icons/hicolor/*/apps/unidocs.png
mkdir -p "$APPS_DIR" "$ICON_DIR"
if [ -f "$INSTALL_DIR/unidocs.png" ]; then
    install -m 644 "$INSTALL_DIR/unidocs.png" "$ICON_DIR/unidocs.png"
fi
cat > "$APPS_DIR/unidocs.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=UniDocs
Comment=Documents, modules and tags
Exec=$BIN_DIR/$APP
Icon=unidocs
Terminal=false
Categories=Office;Utility;
EOF

printf '\nUniDocs installed.\n\n'
case ":$PATH:" in
    *":$BIN_DIR:"*) info "start it with:  unidocs" ;;
    *)  info "add $BIN_DIR to your PATH, then start it with:  unidocs"
        info "or run it directly:  $INSTALL_DIR/$APP" ;;
esac
