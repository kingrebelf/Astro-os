#!/bin/bash
# ASTRO//OS installer for Ubuntu / Debian.
#
#   curl -fsSL https://raw.githubusercontent.com/kingrebelf/Astro-os/main/install.sh | bash
#
# Run it as the user who will use the desktop (not root); it asks for sudo only to install packages.
#
#   --autologin   log this user straight into the desktop at boot (SDDM)
#   --no-data     skip the IP location databases (the globe then shows no cities)
#   --no-start    install only; do not switch the running desktop over now
#   --dir PATH    where to put ASTRO//OS (default: ~/astro-os)
set -Eeuo pipefail

REPO="https://github.com/kingrebelf/Astro-os"
DIR="${ASTRO_DIR:-$HOME/astro-os}"
AUTOLOGIN=0 DATA=1 START=1

while [ $# -gt 0 ]; do
  case "$1" in
    --autologin) AUTOLOGIN=1 ;;
    --no-data)   DATA=0 ;;
    --no-start)  START=0 ;;
    --dir)       DIR="$2"; shift ;;
    -h|--help)   sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

say()  { printf '\033[38;2;0;255;140m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[38;2;255;190;60m!!\033[0m  %s\n' "$*" >&2; }
die()  { printf '\033[38;2;255;43;214mxx\033[0m  %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || die "Run this as your normal user, not root. It uses sudo where needed."
command -v apt-get >/dev/null || die "This installer needs apt (Ubuntu or Debian)."

# ---------------------------------------------------------------- packages
# What ASTRO//OS itself needs.
PKGS=(python3 python3-pyqt6 alacritty fonts-ubuntu papirus-icon-theme x11-apps x11-xserver-utils
      libglib2.0-bin libxtst6 libxext6 pipewire-bin iproute2 pciutils curl git ca-certificates)
# The session it runs on top of. Only added when there is no LXQt yet (a bare server install).
BASE=(lxqt openbox sddm xserver-xorg xserver-xorg-video-all falkon)

NEW_DESKTOP=0
if ! command -v lxqt-session >/dev/null; then
  NEW_DESKTOP=1
  PKGS+=("${BASE[@]}")
fi

missing=()
for p in "${PKGS[@]}"; do
  dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q "install ok installed" || missing+=("$p")
done

if [ ${#missing[@]} -gt 0 ]; then
  say "Installing packages: ${missing[*]}"
  sudo apt-get update
  if [ $NEW_DESKTOP -eq 1 ]; then
    echo "sddm shared/default-x-display-manager select sddm" | sudo debconf-set-selections
  fi
  # --no-install-recommends keeps NetworkManager from being pulled in next to a server's own networking.
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing[@]}"
else
  say "All packages already installed"
fi

if [ $NEW_DESKTOP -eq 1 ]; then
  say "Enabling the graphical login"
  sudo systemctl enable sddm
  sudo systemctl set-default graphical.target
  mkdir -p "$HOME/.config/lxqt"
  [ -f "$HOME/.config/lxqt/session.conf" ] || printf '[General]\nwindow_manager=openbox\n' > "$HOME/.config/lxqt/session.conf"
fi

# ---------------------------------------------------------------- source
HERE=""
[ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ] && HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "$HERE" ] && [ -x "$HERE/astroctl" ]; then
  DIR="$HERE"                                   # running from a checkout or an unpacked download
  say "Using the copy in $DIR"
elif [ -d "$DIR/.git" ]; then
  say "Updating $DIR"
  git -C "$DIR" pull --ff-only
elif [ -e "$DIR" ]; then
  die "$DIR already exists and is not an ASTRO//OS checkout. Move it, or pass --dir."
else
  say "Downloading ASTRO//OS to $DIR"
  git clone --depth 1 "$REPO" "$DIR"
fi

# ---------------------------------------------------------------- location data
# DB-IP Lite (https://db-ip.com, CC BY 4.0). Published monthly; try this month, then the last.
fetch_db() {   # city|asn
  local kind=$1 out="$DIR/data/dbip-$1.mmdb" m url
  [ -s "$out" ] && return 0
  for m in "$(date +%Y-%m)" "$(date -d "$(date +%Y-%m-15) -1 month" +%Y-%m)"; do
    url="https://download.db-ip.com/free/dbip-$kind-lite-$m.mmdb.gz"
    if curl -fsSL "$url" -o "$out.gz"; then
      gunzip -f "$out.gz" && return 0
    fi
    rm -f "$out.gz"
  done
  return 1
}

if [ $DATA -eq 1 ]; then
  say "Fetching the offline IP location databases (about 70 MB)"
  mkdir -p "$DIR/data"
  fetch_db city || warn "City database not downloaded: the globe will show no locations. Re-run install.sh to retry."
  fetch_db asn  || warn "Network-owner database not downloaded: connections will show no owner."
fi

# ---------------------------------------------------------------- set up for this user
say "Building the theme and adding the login hook"
"$DIR/astroctl" install

if [ $AUTOLOGIN -eq 1 ]; then
  say "Turning on automatic login for $USER"
  sudo mkdir -p /etc/sddm.conf.d
  printf '[Autologin]\nUser=%s\nSession=lxqt\nRelogin=false\n' "$USER" | sudo tee /etc/sddm.conf.d/10-autologin.conf >/dev/null
fi

mkdir -p "$HOME/.config/astro-os"
touch "$HOME/.config/astro-os/enabled"           # come up in ASTRO//OS at every login

if [ $START -eq 1 ] && pgrep -u "$USER" -x lxqt-session >/dev/null; then
  say "Switching the running desktop to ASTRO//OS"
  "$DIR/astroctl" on
  echo
  say "Done. ASTRO//OS is on. 'astroctl off' (or NORMAL OS in the dock) goes back."
elif [ $NEW_DESKTOP -eq 1 ]; then
  echo
  say "Done. Reboot to start the desktop:  sudo reboot"
else
  echo
  say "Done. ASTRO//OS starts the next time $USER logs in to LXQt."
fi
