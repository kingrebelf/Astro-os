#!/bin/bash
# Write the ASTRO//OS image to a USB stick.    sudo ./write-usb.sh /dev/sdX
# Everything on that stick is erased. Run 'lsblk' first to find the right device name.
set -euo pipefail
ISO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/out/astro-os-amd64.iso"
dev="${1:-}"
[ -f "$ISO" ] || { echo "No image yet: run sudo ./build.sh first."; exit 1; }
if [ -z "$dev" ] || [ ! -b "$dev" ]; then
  echo "Usage: sudo $0 /dev/sdX"; echo; echo "Removable drives on this machine:"
  lsblk -dno NAME,SIZE,MODEL,TRAN,RM | awk '$NF==1 {print "  /dev/"$0}'
  exit 1
fi
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo."; exit 1; }
[ "$(lsblk -dno RM "$dev")" = 1 ] || [ -n "${FORCE:-}" ] || { echo "$dev is not a removable drive. Set FORCE=1 if you are sure."; exit 1; }
if lsblk -no MOUNTPOINT "$dev" | grep -qE '^/($|boot|home)'; then echo "$dev holds the running system. Refusing."; exit 1; fi
echo "About to ERASE $dev:"; lsblk -o NAME,SIZE,MODEL,MOUNTPOINT "$dev"
read -rp "Type YES to continue: " ok; [ "$ok" = YES ] || exit 1
for p in $(lsblk -lno NAME "$dev" | tail -n +2); do umount "/dev/$p" 2>/dev/null || true; done
dd if="$ISO" of="$dev" bs=4M status=progress oflag=direct conv=fsync
sync; echo "Done. Boot the target machine from this stick."
