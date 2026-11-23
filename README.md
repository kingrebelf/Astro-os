# ASTRO//OS (the operating system)

A small, fast Linux system that boots straight into the [ASTRO//OS](https://github.com/kingrebelf/Astro-os)
command-deck desktop, with OpenCode already installed. It builds into one ISO file that you write to a
USB stick and install on any 64-bit PC or server (old BIOS machines, UEFI, and UEFI with Secure Boot).

## What is in it

| | |
|---|---|
| Base | Debian 13 "trixie", installed without recommended extras, manuals or docs |
| Desktop | The ASTRO//OS shell on Openbox, no compositor, rounded window corners |
| Hardware dashboard | The desktop itself, plus the task manager (`Ctrl+Shift+Esc`) |
| Terminal | Alacritty with the ASTRO profile (`Ctrl+Alt+T`) |
| Files | ASTRO//FILES (`Super+E`) |
| Browser | Firefox ESR with the ASTRO styling (`Super+B`) |
| Editor | FeatherPad (ASTRO menu > TEXT EDITOR), and `nano` in the terminal |
| Settings | LXQt settings (ASTRO menu > SYSTEM SETTINGS), `nmtui` for network and Wi-Fi |
| Themes | ASTRO menu > APPEARANCE / THEMES: presets, accent colours, light mode, rounding, fonts |
| OpenCode | Built into the image. `{} CODE` in the dock, `Super+C`, or `opencode` in a terminal |
| Wispr Flow | `)) FLOW` in the dock. See the note below |
| Installer | Calamares, started with `v INSTALL` in the dock of the live session |

### OpenCode

The OpenCode program is downloaded while the image is built and shipped inside it, so it works on first
boot even with no network. Each account gets its own copy in `~/.opencode/bin`, which is where OpenCode's
own installer puts it, so `opencode upgrade` works. If the copy is ever missing, the dock button and the
`opencode` command download it again before starting.

### Wispr Flow

Wispr has not released Flow for Linux. As of 2026-11-23 their download page offers Mac, Windows, iPhone
and Android, with a "Vote to build for Linux" button. So the `)) FLOW` button cannot install it today.
What it does instead: each time you press it, it checks Wispr's download link for a Linux build. When one
exists it downloads and installs it with one click and from then on starts it. Until then it tells you
there is no Linux version and offers to open their download page. If Wispr publishes the build under a
different link, put it in `/etc/astro-os/flow.conf`.

## Build

On Ubuntu or Debian:

```bash
sudo apt install debootstrap debian-archive-keyring squashfs-tools xorriso mtools dosfstools
```

```bash
sudo ./build.sh
```

The image is written to `out/astro-os-amd64.iso`. The first build downloads about 1 GB of packages;
later builds reuse `build/` and only redo the ASTRO layer and the packing.

## Put it on a USB stick

```bash
sudo ./write-usb.sh /dev/sdX
```

Run it with no device name to list the removable drives. Any image writer (balenaEtcher, Rufus in DD
mode, Ventoy) also works with the ISO.

## Install

Boot the target machine from the stick. It comes up in the live desktop (user `astro`, password `live`).
Press `v INSTALL` in the dock, pick the disk, name the user, and reboot when it finishes. The installer
removes itself and the live-USB machinery from the installed system.

## Layout

| Path | What |
|---|---|
| `build.sh` | The whole build: bootstrap, packages, ASTRO layer, ISO |
| `config/packages.list` | Every package in the system. Add or remove lines here |
| `config/grub.cfg` | Boot menu of the USB stick |
| `shell/` | The ASTRO//OS desktop (copy of the Astro-os repo, see `shell/UPSTREAM_COMMIT`) plus `corners.py` |
| `rootfs/` | Files copied into the system as they are |
| `hooks/` | Scripts run inside the system while it is built |
| `calamares/` | Installer settings and branding |
| `test/vm.sh` | Boots the ISO in QEMU for testing |

Changes made to `shell/` compared with the Astro-os repo: `corners.py` (rounded corners), `palette.py`,
`appearance.py` and `theme/apply.py` (themes), rounded dock buttons, a distro mode in
`astroctl` and `dock.py` (switched on by `/etc/astro-os/distro`), and `theme/rcxml.py` split out of `astroctl`.
On a normal Ubuntu install without that file they behave as before, apart from the rounded corners.

## Themes

ASTRO menu > APPEARANCE / THEMES (or `astroctl launch look`) opens ASTRO//LOOK:

- nine presets: the original Astro Green, five more dark ones, and three light ones
- your own background, accent, second accent, alert, warning and text colours
- dark / light mode switch that keeps your hues
- window corner radius, dock button radius, dock font and weight, text font, 12 / 24 hour clock

APPLY saves to `~/.config/astro-os/theme.json` and reloads the desktop: dashboard, dock, window borders,
cursor, file manager, task manager, settings, terminal and Firefox. A terminal or browser that is already
open keeps its old colours until it is restarted. RESET TO DEFAULT, or `astroctl theme reset`, goes back to
the original look. Put a `theme.json` in `/etc/astro-os/` to change the default for every user.

How it works: `shell/palette.py` moves each colour of the original green look to the matching place in
the chosen palette, so no screen had to be redrawn by hand. With the default theme it changes nothing.

## Rounded corners

`shell/corners.py` rounds every window that has a title bar, using the X Shape extension, so no
compositor is needed. The radius is set in ASTRO//LOOK; `ASTRO_CORNER_RADIUS` overrides it (0 turns it off).
