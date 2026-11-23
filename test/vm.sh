#!/bin/bash
# Boot the ISO (or an installed disk) in a throwaway QEMU machine for testing.
#
#   test/vm.sh live [bios|uefi|secure]     boot the ISO with an empty 24 GB disk attached
#   test/vm.sh disk [bios|uefi|secure]     boot that disk after an install
#   test/vm.sh shot FILE.png               screenshot of the running machine
#   test/vm.sh key  "ctrl-alt-t"           press a key combination (QEMU key names)
#   test/vm.sh type "text"                 type text
#   test/vm.sh click X Y                   left click at screen pixel X,Y
#   test/vm.sh stop
#
# Add GUI=1 to get a window instead of running headless. Serial console log: build/vm/serial.log
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VM="$HERE/build/vm"; mkdir -p "$VM"
QMP="$VM/qmp.sock"
W=${VM_W:-1280}; H=${VM_H:-800}

qmp() { python3 "$HERE/test/qmp.py" "$QMP"; }   # JSON command(s) on stdin, one per line

case "${1:-}" in
  live|disk)
    fw=${2:-bios}; args=()
    case "$fw" in
      uefi)   cp -n /usr/share/OVMF/OVMF_VARS_4M.fd "$VM/vars-uefi.fd"
              args+=(-drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd -drive if=pflash,format=raw,file="$VM/vars-uefi.fd") ;;
      secure) cp -n /usr/share/OVMF/OVMF_VARS_4M.ms.fd "$VM/vars-secure.fd"
              args+=(-machine q35,smm=on -global driver=cfi.pflash01,property=secure,value=on
                     -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.secboot.fd -drive if=pflash,format=raw,file="$VM/vars-secure.fd") ;;
    esac
    [ -f "$VM/disk-$fw.qcow2" ] || qemu-img create -q -f qcow2 "$VM/disk-$fw.qcow2" 24G
    args+=(-drive file="$VM/disk-$fw.qcow2",if=virtio,format=qcow2)
    [ "$1" = live ] && args+=(-cdrom "$HERE/out/astro-os-amd64.iso" -boot d)
    if [ -n "${GUI:-}" ]; then args+=(-display gtk); else args+=(-display none); fi
    rm -f "$QMP"
    exec qemu-system-x86_64 -enable-kvm -cpu host -smp 4 -m 4096 -name astro-os-test \
        -device virtio-vga,xres=$W,yres=$H -device usb-ehci -device usb-tablet -device virtio-rng-pci \
        -netdev user,id=n0 -device virtio-net-pci,netdev=n0 \
        -qmp unix:"$QMP",server,nowait -serial file:"$VM/serial.log" -daemonize -pidfile "$VM/pid" "${args[@]}" ;;
  shot)
    out=$(readlink -f "$2"); ppm="$VM/shot.ppm"
    echo "{\"execute\":\"screendump\",\"arguments\":{\"filename\":\"$ppm\"}}" | qmp
    python3 -c "
import sys
from PyQt6.QtGui import QImage
QImage(sys.argv[1]).save(sys.argv[2])" "$ppm" "$out" ;;
  key)
    keys=$(python3 -c "import sys,json; print(json.dumps([{'type':'qcode','data':k} for k in sys.argv[1].split('-')]))" "$2")
    echo "{\"execute\":\"send-key\",\"arguments\":{\"keys\":$keys}}" | qmp ;;
  type)
    python3 - "$2" <<'PY' | qmp
import json, sys
M = {" ": "spc", "\n": "ret", "-": "minus", ".": "dot", "/": "slash", ",": "comma", "=": "equal", ";": "semicolon",
     "_": "shift-minus", ":": "shift-semicolon", "|": "shift-backslash", "&": "shift-7", "'": "apostrophe",
     ">": "shift-dot", "<": "shift-comma", "$": "shift-4", "(": "shift-9", ")": "shift-0", "\"": "shift-apostrophe",
     "*": "shift-8", "~": "shift-grave_accent", "!": "shift-1", "@": "shift-2", "+": "shift-equal", "?": "shift-slash"}
for ch in sys.argv[1]:
    k = M.get(ch) or (("shift-" + ch.lower()) if ch.isupper() else ch)
    print(json.dumps({"execute": "send-key", "arguments": {"keys": [{"type": "qcode", "data": x} for x in k.split("-", 1 if k.startswith("shift-") else 0)]}}))
PY
    ;;
  click)
    x=$(( $2 * 32767 / W )); y=$(( $3 * 32767 / H ))
    { echo "{\"execute\":\"input-send-event\",\"arguments\":{\"events\":[{\"type\":\"abs\",\"data\":{\"axis\":\"x\",\"value\":$x}},{\"type\":\"abs\",\"data\":{\"axis\":\"y\",\"value\":$y}}]}}"
      echo "{\"execute\":\"input-send-event\",\"arguments\":{\"events\":[{\"type\":\"btn\",\"data\":{\"down\":true,\"button\":\"left\"}}]}}"
      echo "{\"execute\":\"input-send-event\",\"arguments\":{\"events\":[{\"type\":\"btn\",\"data\":{\"down\":false,\"button\":\"left\"}}]}}"; } | qmp ;;
  stop) [ -f "$VM/pid" ] && kill "$(cat "$VM/pid")" 2>/dev/null; rm -f "$VM/pid" ;;
  *) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
