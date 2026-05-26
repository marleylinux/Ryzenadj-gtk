# ryzenadj-gtk

GTK4 frontend for ryzenadj. Just lets you change power limits, currents, temps and curve optimizer without living in the terminal.

I made it for myself because I was tired of typing the same commands over and over.

Powered by [RyzenAdj](https://github.com/flygoat/ryzenadj)

## What it does

- Dashboard showing current power, current, temps and some clock speeds
- Curve optimizer with all-core, iGPU and per-core sliders (-30 to +30)
- Power limits (STAPM, fast PPT, slow PPT, APU PPT)
- Current limits (TDC and EDC for CPU and SoC)
- Temperature limits and skin temp stuff
- iGPU clock limits and forcing
- Some SoC clock and other lower level options
- Save your own profiles and switch between them easily
- Auto switch profiles when you plug or unplug the charger
- Re-applies your settings after sleep (usually within a few seconds)
- Keeps re-applying in the background every so often so the firmware doesn't override you
- Shows a warning if Secure Boot or kernel lockdown is blocking things
- Enthusiast mode if you want to push past the normal limits (250W etc)

## Curve optimizer

This is the part I actually care about most. You get separate sliders for each core now instead of just one global offset. Negative numbers reduce voltage.

The app clamps to the safe -30 to +30 range. It also asks before applying anything that looks risky (big CO changes or stupid high power limits).

## Warnings

`ryzenadj` needs root access to the hardware. The install script and AUR package drop a sudoers file so you don't get spammed with password prompts every second. It's pretty narrow (only ryzenadj and the service commands).

If that file isn't there the app will just show a page telling you to reboot.

Be careful with this tool. Too much power or too aggressive undervolting can make the machine unstable or hotter than expected. The confirmation dialogs are there for a reason.

## Requirements

- Python 3.11+
- gtk4 + libadwaita + python-gobject
- ryzenadj installed
- The sudoers rule (added by the installer)

## Install

**Arch (easiest):**

```bash
yay -S ryzenadj-gtk
```

Or build from this repo:

```bash
git clone https://github.com/marleylinux/Ryzenadj-gtk
cd Ryzenadj-gtk
makepkg -si
```

**Other distros:**

```bash
git clone https://github.com/marleylinux/Ryzenadj-gtk
cd Ryzenadj-gtk
sudo ./install.sh
```

Then launch "Ryzenadj-gtk" from your menu or just run `ryzenadj-gtk`.

## Uninstall

```bash
sudo ./uninstall.sh
```

## License

GPL-3.0
