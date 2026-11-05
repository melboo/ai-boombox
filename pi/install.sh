#!/bin/bash
# Boombox Visuals v3 - installer for Raspberry Pi OS (64-bit, desktop)
# Run from inside the pi/ folder:   bash install.sh
# Optional: JETSON_URL=http://192.168.1.50:8765 bash install.sh
# Safe to run again (e.g. after an update).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "== 1/6 Installing system packages (needs your password) =="
sudo apt update
sudo apt install -y python3-venv python3-pip pulseaudio-utils \
    bluez bluez-tools libsdl2-2.0-0 libsdl2-ttf-2.0-0 libsdl2-mixer-2.0-0

echo "== 2/6 Python environment in ~/boombox-venv =="
python3 -m venv ~/boombox-venv
~/boombox-venv/bin/pip install --upgrade pip
~/boombox-venv/bin/pip install -r "$HERE/requirements.txt"
chmod +x "$HERE"/*.sh "$HERE"/*.py

echo "== 3/6 Settings (config.json) =="
if [ ! -f "$HERE/config.json" ]; then
    cp "$HERE/config.example.json" "$HERE/config.json"
fi
if [ -n "$JETSON_URL" ]; then
    python3 - "$HERE/config.json" "$JETSON_URL" <<'EOF'
import json, sys
p, url = sys.argv[1], sys.argv[2]
c = json.load(open(p)); c["jetson_url"] = url; json.dump(c, open(p, "w"), indent=2)
EOF
fi
echo "   Jetson address: $(python3 -c "import json;print(json.load(open('$HERE/config.json'))['jetson_url'])")"
# Spotify Connect (v2) is switched off: Spotify blocks librespot's audio keys.
systemctl --user disable --now boombox-spotify.service 2>/dev/null || true

echo "== 4/6 Bluetooth speaker =="
sudo rfkill unblock bluetooth || true
# Announce the Pi as a loudspeaker so phones send it media audio
sudo sed -i 's/^#\?Class = .*/Class = 0x200414/' /etc/bluetooth/main.conf || true
sudo systemctl restart bluetooth || true
sleep 2
bluetoothctl power on >/dev/null || true
bluetoothctl system-alias Boombox >/dev/null || true
wpctl set-volume @DEFAULT_AUDIO_SINK@ 100% 2>/dev/null || true

echo "== 5/6 Start the visuals automatically when the Pi switches on =="
sudo raspi-config nonint do_boot_behaviour B4 || true   # desktop autologin
sudo raspi-config nonint do_blanking 1 || true          # never blank the screen
mkdir -p ~/.config/autostart ~/.config/labwc
cat > ~/.config/autostart/boombox.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Boombox Visuals
Exec=$HERE/run.sh
X-GNOME-Autostart-enabled=true
EOF
touch ~/.config/labwc/autostart
sed -i '/run\.sh &$/d' ~/.config/labwc/autostart       # remove older Boombox versions
echo "$HERE/run.sh &" >> ~/.config/labwc/autostart

echo "== 6/6 Music folder ~/Music/boombox =="
mkdir -p ~/Music/boombox

echo
echo "Done."
echo "  Bluetooth: run ./pair.sh once, then pair 'Boombox' on your phone."
echo "  Visuals:   ./restart.sh   (after this they start by themselves)"
echo "  AI images: start the dream server on the Jetson; the Pi finds it at the address above."
