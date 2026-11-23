# Base system identity and boot-speed settings. Runs inside the image.
V="$ASTRO_VERSION"

sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen
locale-gen >/dev/null
update-locale LANG=en_US.UTF-8
ln -sf /usr/share/zoneinfo/UTC /etc/localtime
echo astro-os > /etc/hostname
printf '127.0.0.1\tlocalhost\n127.0.1.1\tastro-os\n::1\tlocalhost ip6-localhost ip6-loopback\n' > /etc/hosts

# Our name on the system. The divert keeps Debian's base-files updates from putting theirs back.
dpkg-divert --quiet --local --rename --add /usr/lib/os-release 2>/dev/null || true
cat > /usr/lib/os-release <<OS
PRETTY_NAME="ASTRO//OS $V"
NAME="ASTRO//OS"
VERSION_ID="$V"
VERSION="$V (Debian 13 base)"
VERSION_CODENAME=trixie
ID=astro-os
ID_LIKE=debian
HOME_URL="https://github.com/kingrebelf/Astro-os"
OS
ln -sf ../usr/lib/os-release /etc/os-release
printf 'ASTRO//OS %s \\n \\l\n\n' "$V" > /etc/issue

# --- boot speed: nothing waits for the network, nothing runs housekeeping at startup
systemctl set-default graphical.target >/dev/null
systemctl enable lightdm NetworkManager systemd-timesyncd >/dev/null 2>&1 || true
systemctl mask NetworkManager-wait-online.service systemd-networkd-wait-online.service >/dev/null 2>&1
for u in apt-daily.timer apt-daily-upgrade.timer dpkg-db-backup.timer e2scrub_all.timer e2scrub_reap.service; do
  systemctl disable "$u" >/dev/null 2>&1 || true
done
# LightDM's default is to wait for a (non-existent) boot splash to quit
mkdir -p /etc/systemd/system/lightdm.service.d
printf '[Unit]\nAfter=\nAfter=systemd-user-sessions.service dbus.service\n' > /etc/systemd/system/lightdm.service.d/10-fast.conf

# let the desktop user manage network connections without a password prompt
mkdir -p /etc/polkit-1/rules.d
cat > /etc/polkit-1/rules.d/50-astro-network.rules <<'RULE'
polkit.addRule(function(action, subject) {
  if (action.id.indexOf("org.freedesktop.NetworkManager.") == 0 && subject.isInGroup("netdev") && subject.local) {
    return polkit.Result.YES;
  }
});
RULE
