#!/bin/bash
# Switch the Pi's picture between HDMI and the built-in composite (analog PAL) output.
#   ./tvout.sh composite   picture + sound through the 3.5 mm jack -> AV cable -> converter AV IN
#   ./tvout.sh hdmi        picture + sound through HDMI -> converter HDMI IN (default)
# The Pi restarts afterwards. On the converter, slide the input switch to match.
#
# Composite needs a 4-pole 3.5 mm to 3x RCA cable wired for the Raspberry Pi
# (tip = left, ring 1 = right, ring 2 = ground, sleeve = video). With other cables,
# try the red or white plug in the converter's yellow input if yellow shows nothing.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
CFG=/boot/firmware/config.txt
CMD=/boot/firmware/cmdline.txt
MODE="$1"

set_output() {
    python3 - "$HERE/config.json" "$1" <<'EOF'
import json, sys
path, out = sys.argv[1], sys.argv[2]
try:
    cfg = json.load(open(path))
except Exception:
    cfg = {}
cfg["output"] = out
json.dump(cfg, open(path, "w"), indent=2)
EOF
}

case "$MODE" in
  composite)
    sudo cp "$CFG" "$CFG.boombox-backup"
    sudo cp "$CMD" "$CMD.boombox-backup"
    sudo sed -i 's/^dtoverlay=vc4-kms-v3d.*/dtoverlay=vc4-kms-v3d,composite/' "$CFG"
    grep -q '^enable_tvout=1' "$CFG" || echo 'enable_tvout=1' | sudo tee -a "$CFG" >/dev/null
    sudo sed -i 's/ video=[^ ]*//g' "$CMD"
    sudo sed -i '1 s/$/ video=Composite-1:720x576@50ie/' "$CMD"
    set_output analog
    echo "Composite PAL output on. Converter switch -> AV. Restarting..."
    ;;
  hdmi)
    sudo sed -i 's/^dtoverlay=vc4-kms-v3d,composite/dtoverlay=vc4-kms-v3d/' "$CFG"
    sudo sed -i '/^enable_tvout=1/d' "$CFG"
    sudo sed -i 's/ video=[^ ]*//g' "$CMD"
    set_output hdmi
    echo "HDMI output on. Converter switch -> HDMI. Restarting..."
    ;;
  *)
    echo "Usage: ./tvout.sh composite   or   ./tvout.sh hdmi"
    exit 1
    ;;
esac
sleep 2
sudo reboot
