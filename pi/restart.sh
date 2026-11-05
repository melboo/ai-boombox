#!/bin/bash
# Restart the visuals on the boombox screen (works over SSH from your laptop).
#   ./restart.sh                       live mode (Bluetooth)
#   ./restart.sh --files test_music    play the test song
HERE="$(cd "$(dirname "$0")" && pwd)"
pkill -f "boombox-venv/bin/python player.py" 2>/dev/null
sleep 2
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export DISPLAY=:0
export WAYLAND_DISPLAY=wayland-0
setsid nohup "$HERE/run.sh" "$@" >/tmp/boombox.log 2>&1 < /dev/null &
echo "Visuals restarted. Look at the boombox screen. (Log: /tmp/boombox.log)"
