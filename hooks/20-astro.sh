# The ASTRO//OS look: cursor + window theme system-wide, and the per-user defaults in /etc/skel.
A=/opt/astro-os
export HOME=/tmp/astro-theme QT_QPA_PLATFORM=offscreen
rm -rf "$HOME"; mkdir -p "$HOME"
python3 "$A/theme/build.py"
rm -rf /usr/share/icons/AstroOS /usr/share/themes/AstroOS
mv "$HOME/.icons/AstroOS" /usr/share/icons/AstroOS
mv "$HOME/.themes/AstroOS" /usr/share/themes/AstroOS
rm -rf "$HOME"

mkdir -p /etc/skel/.config/openbox /etc/skel/.config/lxqt
python3 "$A/theme/rcxml.py" /etc/xdg/openbox/rc.xml /etc/skel/.config/openbox/rc.xml astro-os-managed --keys
cp "$A/theme/lxqt.conf" /etc/skel/.config/lxqt/lxqt.conf
ln -sf "$A/astroctl" /usr/local/bin/astroctl

# the greeter and anything started outside the session use the same pointer
mkdir -p /usr/share/icons/default
printf '[Icon Theme]\nInherits=AstroOS\n' > /usr/share/icons/default/index.theme

# offline IP location databases for the globe (DB-IP Lite, CC BY 4.0), same source as install.sh
mkdir -p "$A/data"
for kind in city asn; do
  out="$A/data/dbip-$kind.mmdb"
  [ -s "$out" ] && continue
  for m in "$(date +%Y-%m)" "$(date -d "$(date +%Y-%m-15) -1 month" +%Y-%m)"; do
    if curl -fsSL "https://download.db-ip.com/free/dbip-$kind-lite-$m.mmdb.gz" -o "$out.gz"; then gunzip -f "$out.gz"; break; fi
    rm -f "$out.gz"
  done
  [ -s "$out" ] || echo "WARNING: $kind database not downloaded; the globe will show less"
done

python3 -m compileall -q "$A" >/dev/null || true

# installer branding: version, artwork, and the same widget styling as the rest of the desktop
B=/etc/calamares/branding/astro
sed -i "s/@VERSION@/$ASTRO_VERSION/g" "$B/branding.desc"
python3 "$B/mkimages.py" && rm -f "$B/mkimages.py"
cp "$A/theme/astro.qss" "$B/stylesheet.qss"
