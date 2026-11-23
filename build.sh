#!/bin/bash
# Build the ASTRO//OS install image.
#
#   sudo ./build.sh            run every stage that is not done yet, then build the ISO
#   sudo ./build.sh packages   (re)install the package set into the root filesystem
#   sudo ./build.sh customize  (re)apply rootfs/, shell/, calamares/ and the hooks
#   sudo ./build.sh iso        pack the root filesystem into out/astro-os-amd64.iso
#   sudo ./build.sh shell      open a shell inside the root filesystem
#   sudo ./build.sh clean      delete build/ (the next build starts from nothing)
#
# Needs: debootstrap debian-archive-keyring squashfs-tools xorriso mtools dosfstools
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="$HERE/build"
ROOT="$BUILD/chroot"
ISO="$BUILD/iso"
OUT="$HERE/out/astro-os-amd64.iso"
SUITE=trixie
MIRROR=http://deb.debian.org/debian
VERSION="$(cat "$HERE/config/version")"
LABEL=ASTRO_OS

say() { printf '\033[38;2;0;255;140m==>\033[0m %s\n' "$*"; }
die() { printf '\033[38;2;255;43;214mxx\033[0m  %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || die "Run with sudo."

# ---------------------------------------------------------------- chroot plumbing
mounted=0
enter() {
  [ $mounted -eq 1 ] && return
  mount -t proc proc "$ROOT/proc"
  mount -t sysfs sys "$ROOT/sys"
  mount --bind /dev "$ROOT/dev"
  mount -t devpts devpts "$ROOT/dev/pts"
  cp /etc/resolv.conf "$ROOT/etc/resolv.conf"
  # nothing inside the image may start a service while we are building it
  printf '#!/bin/sh\nexit 101\n' > "$ROOT/usr/sbin/policy-rc.d"; chmod +x "$ROOT/usr/sbin/policy-rc.d"
  echo force-unsafe-io > "$ROOT/etc/dpkg/dpkg.cfg.d/99build-fast"     # build only: skip the per-file disk sync
  mounted=1
}
leave() {
  [ $mounted -eq 1 ] || return 0
  rm -f "$ROOT/usr/sbin/policy-rc.d" "$ROOT/etc/dpkg/dpkg.cfg.d/99build-fast"
  for m in dev/pts dev sys proc; do umount -l "$ROOT/$m" 2>/dev/null || true; done
  mounted=0
}
trap leave EXIT
run() { enter; chroot "$ROOT" /usr/bin/env -i HOME=/root TERM="${TERM:-xterm}" LC_ALL=C.UTF-8 \
          PATH=/usr/sbin:/usr/bin:/sbin:/bin DEBIAN_FRONTEND=noninteractive ASTRO_VERSION="$VERSION" "$@"; }

# ---------------------------------------------------------------- stages
stage_base() {
  say "Bootstrapping Debian $SUITE"
  mkdir -p "$BUILD"
  debootstrap --arch=amd64 --variant=minbase --components=main,contrib,non-free,non-free-firmware \
      --include=ca-certificates,apt-utils "$SUITE" "$ROOT" "$MIRROR"
}

stage_packages() {
  say "Installing packages"
  cat > "$ROOT/etc/apt/sources.list" <<EOF
deb $MIRROR $SUITE main contrib non-free non-free-firmware
deb $MIRROR $SUITE-updates main contrib non-free non-free-firmware
deb http://security.debian.org/debian-security $SUITE-security main contrib non-free non-free-firmware
EOF
  # lean by default: no recommended extras, no manuals or bundled docs
  printf 'APT::Install-Recommends "false";\nAPT::Install-Suggests "false";\n' > "$ROOT/etc/apt/apt.conf.d/90astro-lean"
  cat > "$ROOT/etc/dpkg/dpkg.cfg.d/90astro-lean" <<'EOF'
path-exclude=/usr/share/man/*
path-exclude=/usr/share/doc/*
path-include=/usr/share/doc/*/copyright
path-exclude=/usr/share/info/*
EOF
  local pkgs
  pkgs=$(sed 's/#.*//' "$HERE/config/packages.list" | xargs)
  run apt-get update
  run apt-get -y dist-upgrade
  # shellcheck disable=SC2086
  run apt-get -y install $pkgs
  run apt-get -y autoremove --purge
  run apt-get clean
  sha256sum "$HERE/config/packages.list" > "$BUILD/.packages.done"
}

stage_customize() {
  say "Applying the ASTRO//OS layer"
  rm -rf "$ROOT/opt/astro-os"
  mkdir -p "$ROOT/opt/astro-os"
  cp -a "$HERE/shell/." "$ROOT/opt/astro-os/"
  find "$ROOT/opt/astro-os" -name __pycache__ -prune -exec rm -rf {} +
  cp -a "$HERE/rootfs/." "$ROOT/"
  rm -rf "$ROOT/etc/calamares"
  mkdir -p "$ROOT/etc/calamares"
  cp -a "$HERE/calamares/." "$ROOT/etc/calamares/"
  chown -R root:root "$ROOT/opt/astro-os" "$ROOT/etc/calamares" "$ROOT/etc/skel" "$ROOT/usr/local"
  echo "$VERSION" > "$ROOT/etc/astro-os/version"
  rm -rf "$ROOT/tmp/hooks"; mkdir -p "$ROOT/tmp/hooks"
  cp "$HERE"/hooks/*.sh "$ROOT/tmp/hooks/"
  for h in "$ROOT"/tmp/hooks/*.sh; do
    say "hook $(basename "$h")"
    run bash -e "/tmp/hooks/$(basename "$h")"
  done
  rm -rf "$ROOT/tmp/hooks"
  touch "$BUILD/.customize.done"
}

stage_iso() {
  say "Packing the root filesystem"
  leave
  rm -rf "$ISO"; mkdir -p "$ISO/live" "$ISO/boot/grub" "$ISO/EFI/BOOT" "$ISO/EFI/debian" "$(dirname "$OUT")"
  cp "$(ls -1v "$ROOT"/boot/vmlinuz-* | tail -1)" "$ISO/live/vmlinuz"
  cp "$(ls -1v "$ROOT"/boot/initrd.img-* | tail -1)" "$ISO/live/initrd.img"
  rm -f "$ROOT/etc/resolv.conf"; : > "$ROOT/etc/machine-id"
  mksquashfs "$ROOT" "$ISO/live/filesystem.squashfs" -noappend -comp zstd -Xcompression-level "${SQUASH_LEVEL:-19}" -b 1M \
      -e boot/vmlinuz-* -e boot/initrd.img-* -e "tmp/*" -e "var/cache/apt/archives/*.deb" -e "var/lib/apt/lists/*_*" \
      -wildcards -quiet
  du -sx --block-size=1 "$ROOT" | cut -f1 > "$ISO/live/filesystem.size"
  touch "$ISO/.astro-os-live"
  echo "$VERSION" > "$ISO/.astro-os-version"

  say "Boot loader (BIOS + UEFI with Secure Boot)"
  sed "s/@VERSION@/$VERSION/g" "$HERE/config/grub.cfg" > "$ISO/boot/grub/grub.cfg"
  local G="$ROOT/usr/lib/grub"
  # BIOS: our own core image, modules from the Debian grub in the image
  mkdir -p "$ISO/boot/grub/i386-pc"
  cp "$G"/i386-pc/*.mod "$G"/i386-pc/*.lst "$ISO/boot/grub/i386-pc/"
  # the chroot's own grub-mkimage so the core and the modules always match
  mkdir -p "$ROOT/tmp/grub"
  chroot "$ROOT" grub-mkimage -O i386-pc-eltorito -p /boot/grub -o /tmp/grub/eltorito.img \
      biosdisk iso9660 part_msdos part_gpt normal search search_fs_file configfile linux echo all_video gfxterm test
  cp "$ROOT/tmp/grub/eltorito.img" "$ISO/boot/grub/i386-pc/eltorito.img"
  cp "$G/i386-pc/boot_hybrid.img" "$BUILD/boot_hybrid.img"
  rm -rf "$ROOT/tmp/grub"
  # UEFI: Debian's signed shim + grub. The signed grub reads EFI/debian/grub.cfg, which hops to ours.
  cp "$ROOT/usr/lib/shim/shimx64.efi.signed" "$ISO/EFI/BOOT/BOOTX64.EFI"
  cp "$ROOT/usr/lib/shim/mmx64.efi.signed" "$ISO/EFI/BOOT/mmx64.efi"
  cp "$G/x86_64-efi-signed/grubx64.efi.signed" "$ISO/EFI/BOOT/grubx64.efi"
  cat > "$ISO/EFI/debian/grub.cfg" <<'EOF'
search --no-floppy --set=root --file /.astro-os-live
set prefix=($root)/boot/grub
configfile ($root)/boot/grub/grub.cfg
EOF
  local esp="$BUILD/efi.img"
  rm -f "$esp"; truncate -s 12M "$esp"; mkfs.vfat -n ASTROEFI "$esp" >/dev/null
  mmd -i "$esp" ::EFI ::EFI/BOOT ::EFI/debian
  mcopy -i "$esp" "$ISO"/EFI/BOOT/* ::EFI/BOOT/
  mcopy -i "$esp" "$ISO/EFI/debian/grub.cfg" ::EFI/debian/

  say "Writing $OUT"
  xorriso -as mkisofs -iso-level 3 -full-iso9660-filenames -joliet -rock -volid "$LABEL" \
      -eltorito-boot boot/grub/i386-pc/eltorito.img -no-emul-boot -boot-load-size 4 -boot-info-table --grub2-boot-info \
      --grub2-mbr "$BUILD/boot_hybrid.img" \
      -eltorito-alt-boot -e --interval:appended_partition_2:all:: -no-emul-boot \
      -append_partition 2 C12A7328-F81F-11D2-BA4B-00A0C93EC93B "$esp" -appended_part_as_gpt \
      -o "$OUT" "$ISO" 2>&1 | tail -3
  [ -n "${SUDO_UID:-}" ] && chown "$SUDO_UID:${SUDO_GID:-$SUDO_UID}" "$OUT" "$(dirname "$OUT")"
  say "Done: $OUT ($(du -h "$OUT" | cut -f1))"
}

case "${1:-all}" in
  all)
    [ -x "$ROOT/usr/bin/apt-get" ] || stage_base
    sha256sum -c "$BUILD/.packages.done" >/dev/null 2>&1 || stage_packages
    stage_customize
    stage_iso ;;
  base)      stage_base ;;
  packages)  stage_packages ;;
  customize) stage_customize ;;
  iso)       stage_iso ;;
  shell)     run bash ;;
  clean)     leave; rm -rf --one-file-system "$BUILD" ;;
  *) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
