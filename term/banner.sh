#!/bin/bash
g=$'\e[38;2;0;255;140m'; c=$'\e[38;2;0;229;255m'; d=$'\e[38;2;31;115;80m'; w=$'\e[38;2;220;255;240m'; a=$'\e[38;2;255;190;60m'; r=$'\e[0m'
logo=(
'    ___   _____________  ____     ____ ____  _____'
'   /   | / ___/_  __/ / / __ \   / // // __ \/ ___/'
'  / /| | \__ \ / / / /_/ / / /  / // // / / /\__ \ '
' / ___ |___/ // / / _, _/ /_/ / / // // /_/ /___/ / '
'/_/  |_/____//_/ /_/ |_|\____/ /_//_/ \____//____/  '
)
for l in "${logo[@]}"; do printf '%s%s%s\n' "$g" "$l" "$r"; sleep 0.03; done
mem=$(free -h | awk '/Mem:/{print $3" / "$2}')
ip=$(hostname -I 2>/dev/null | awk '{print $1}')
gpu=$(ls /proc/driver/nvidia/gpus 2>/dev/null | wc -l)
up=$(uptime -p | sed 's/up //')
row() { printf ' %s%-8s%s %s%s%s\n' "$d" "$1" "$r" "$2" "$3" "$r"; sleep 0.03; }
printf '%s %s%s\n' "$d" '──────────────────────────────────────────────────' "$r"
row NODE   "$w" "$(hostname) // $ip"
row CORES  "$g" "$(nproc) threads online"
row MEMORY "$g" "$mem"
gpus=$(lspci 2>/dev/null | grep -ci 'vga.*nvidia')
row GPU    "$a" "$gpu/$gpus online"
row UPTIME "$c" "$up"
printf '%s %s%s\n\n' "$d" '──────────────────────────────────────────────────' "$r"
