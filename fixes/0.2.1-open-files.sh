#!/bin/sh
# ASTRO//OS 0.2.0 -> 0.2.1 fix for an already-installed machine: double-clicking a file opened nothing.
#
#   curl -fsSL https://raw.githubusercontent.com/kingrebelf/Astro-os/linux-iso/fixes/0.2.1-open-files.sh | sudo sh
#
# Installs the qtxdg-mat stand-in, the default-app list, the ASTRO text editor launcher and the
# updated file manager, and gives the text editor the dark ASTRO background.
# Log out and back in (or restart ASTRO//FILES) afterwards.
set -eu
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
BASE=https://raw.githubusercontent.com/kingrebelf/Astro-os/linux-iso
get() {   # get <path in repo> <destination> <mode>
  tmp=$(mktemp)
  curl -fsSL "$BASE/$1" -o "$tmp"
  install -D -m "$3" "$tmp" "$2"
  rm -f "$tmp"
  echo "updated $2"
}
get rootfs/usr/local/bin/qtxdg-mat                    /usr/local/bin/qtxdg-mat                    755
get rootfs/etc/xdg/mimeapps.list                      /etc/xdg/mimeapps.list                      644
get rootfs/usr/share/applications/astro-editor.desktop /usr/share/applications/astro-editor.desktop 644
get shell/files.py                                    /opt/astro-os/files.py                      644
get shell/theme/apply.py                              /opt/astro-os/theme/apply.py                644
update-desktop-database -q /usr/share/applications || true
# dark editor text area for every existing account (light themes switch it back when applied)
for h in /home/*; do
  [ -d "$h" ] || continue
  u=$(stat -c %U "$h")
  su "$u" -c 'python3 /opt/astro-os/theme/apply.py' >/dev/null 2>&1 || true
done
echo "Done. Close and reopen ASTRO//FILES, then double-click a .txt file."
