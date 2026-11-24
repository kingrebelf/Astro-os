#!/usr/bin/env python3
"""Write the active theme (palette.py) into everything that is not drawn by the shell itself:
the Qt stylesheet, terminal colours and prompt, Qt palette, window borders, cursor and Firefox.

    apply.py            generate for the current user
    apply.py --reset    delete the theme file first (back to the original look)

Generated files go to ~/.config/astro-os/gen; astroctl uses them when they exist.
"""
import glob
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import palette

HOME = os.path.expanduser("~")
CONF = os.path.join(HOME, ".config", "astro-os")
GEN = os.path.join(CONF, "gen")
MARK = "astro-os-managed"
SYSTEM_THEME = os.path.isdir("/usr/share/icons/AstroOS")     # the distro ships the default look system-wide


def write(path, text, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    if mode:
        os.chmod(path, mode)


def ini_set(path, section, values):
    """Set keys in one section of a Qt-style .ini file, keeping everything else the program saved there."""
    try:
        lines = open(path).read().splitlines()
    except OSError:
        lines = []
    out, inside, left = [], False, dict(values)
    for line in lines + ["[]"]:
        if line.startswith("["):
            if inside:
                out += ["%s=%s" % kv for kv in left.items()]
                left = {}
            inside = line.strip() == "[%s]" % section
        elif inside and line.split("=", 1)[0] in left:
            key = line.split("=", 1)[0]
            line = "%s=%s" % (key, left.pop(key))
        out.append(line)
    out.pop()
    if left:
        out += ["", "[%s]" % section] + ["%s=%s" % kv for kv in left.items()]
    write(path, "\n".join(out).lstrip("\n") + "\n")


def main():
    if "--reset" in sys.argv:
        try:
            os.remove(palette.USER_FILE)
        except OSError:
            pass
    pal = palette.Palette()
    theme = pal.theme
    read = lambda *p: open(os.path.join(ROOT, *p)).read()

    shutil.rmtree(GEN, ignore_errors=True)
    custom = not pal.identity or theme["ui_font"] != palette.DEFAULT["ui_font"]
    if custom:
        font = theme["ui_font"]
        qss = pal.text(read("theme", "astro.qss")).replace('"Ubuntu Mono"', '"%s"' % font)
        write(os.path.join(GEN, "astro.qss"), qss)
        term = pal.text(read("term", "alacritty.toml")).replace('"Ubuntu Mono"', '"%s"' % font)
        write(os.path.join(GEN, "alacritty.toml"), term)
        write(os.path.join(GEN, "bashrc"), pal.text(read("term", "bashrc")))
        write(os.path.join(GEN, "banner.sh"), pal.text(read("term", "banner.sh")), 0o755)
        for name in ("userChrome.css", "userContent.css", "user.js"):
            text = pal.text(read("theme", "firefox", name))
            if pal.light:
                text = text.replace("firefox-compact-dark@mozilla.org", "firefox-compact-light@mozilla.org")
                text = text.replace('"ui.systemUsesDarkTheme", 1', '"ui.systemUsesDarkTheme", 0')
            write(os.path.join(GEN, "firefox", name), text)

    # Qt palette for every other Qt program
    lxqt = pal.text(read("theme", "lxqt.conf")).replace("Ubuntu Mono,", theme["ui_font"] + ",")
    if pal.light:
        lxqt = lxqt.replace("icon_theme=Papirus-Dark", "icon_theme=Papirus-Light")
    write(os.path.join(HOME, ".config", "lxqt", "lxqt.conf"), lxqt)

    # FeatherPad paints its text area itself: switch its own dark scheme to match the theme
    ini_set(os.path.join(HOME, ".config", "featherpad", "fp.conf"), "text",
            {"darkColorScheme": "false" if pal.light else "true", "darkBgColorValue": "10"})

    # cursor + window borders. On the distro the default look is already in /usr/share,
    # so a per-user copy is only needed (and only kept) for a custom theme.
    icons, themes = os.path.join(HOME, ".icons", "AstroOS"), os.path.join(HOME, ".themes", "AstroOS")
    if pal.identity and SYSTEM_THEME:
        shutil.rmtree(icons, ignore_errors=True)
        shutil.rmtree(themes, ignore_errors=True)
    else:
        subprocess.run([sys.executable, os.path.join(ROOT, "theme", "build.py")], check=True,
                       stdout=subprocess.DEVNULL, env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))

    # Firefox profiles that we manage
    src = os.path.join(GEN, "firefox") if custom else os.path.join(ROOT, "theme", "firefox")
    for base in (os.path.join(HOME, "snap/firefox/common/.mozilla/firefox"), os.path.join(HOME, ".mozilla/firefox")):
        for prof in glob.glob(os.path.join(base, "*.default*")):
            for name, dest in (("userChrome.css", "chrome/userChrome.css"), ("userContent.css", "chrome/userContent.css"),
                               ("user.js", "user.js")):
                target = os.path.join(prof, dest)
                try:
                    ours = not os.path.exists(target) or MARK in open(target).read()
                except OSError:
                    ours = False
                if ours:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    shutil.copy(os.path.join(src, name), target)
    print("theme applied:", theme["name"])


if __name__ == "__main__":
    main()
