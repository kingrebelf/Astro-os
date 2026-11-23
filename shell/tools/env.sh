# source me: borrow the desktop session's environment when run from ssh
if [ -z "$DISPLAY" ]; then
  _pid=$(pgrep -u "$USER" -x openbox | head -1)
  if [ -n "$_pid" ]; then
    while IFS= read -r -d '' kv; do
      case "$kv" in DISPLAY=*|XAUTHORITY=*|DBUS_SESSION_BUS_ADDRESS=*|XDG_RUNTIME_DIR=*|XDG_CONFIG_DIRS=*|XDG_DATA_DIRS=*|XDG_CURRENT_DESKTOP=*) export "$kv";; esac
    done < /proc/$_pid/environ
  fi
fi
export QT_QPA_PLATFORMTHEME= QT_STYLE_OVERRIDE=Fusion QT_ACCESSIBILITY=0
