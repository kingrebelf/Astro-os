# Trim what the build left behind and rebuild the boot image with the live-boot scripts in it.
apt-get clean
rm -rf /var/lib/apt/lists/*_* /var/log/*.log /var/log/apt/* /var/cache/debconf/*-old /root/.cache /root/.bash_history
rm -f /etc/ssh/ssh_host_* /var/lib/dbus/machine-id
update-initramfs -u -k all 2>&1 | grep -v '^W: Possible missing firmware' || true
# tell systemd nothing changed since the image was made, so first boot skips ldconfig and friends
touch /etc/.updated /var/.updated
