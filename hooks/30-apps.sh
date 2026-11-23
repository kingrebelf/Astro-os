# OpenCode is baked into the image, so it is there on first boot even with no network.
# It lives in /etc/skel so every new account gets its own copy in ~/.opencode/bin (where 'opencode upgrade' expects it).
if [ ! -x /etc/skel/.opencode/bin/opencode ] || [ -n "${ASTRO_REFRESH_OPENCODE:-}" ]; then
  HOME=/etc/skel OPENCODE_VARIANT=linux-x64-baseline /usr/local/bin/astro-opencode-install
fi
rm -rf /etc/skel/.cache /etc/skel/.local/share/opencode /etc/skel/.config/opencode

# the terminal profile: make sure ~/.local/bin and OpenCode are on the PATH
grep -q astro-os /etc/skel/.bashrc 2>/dev/null || cat >> /etc/skel/.bashrc <<'RC'

# astro-os: user programs
PATH="$HOME/.local/bin:$HOME/.opencode/bin:$PATH"
RC
