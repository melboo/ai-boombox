#!/bin/bash
# Start Boombox Visuals. Extra options are passed on, e.g.  ./run.sh --windowed
cd "$(dirname "$0")"

# Where the sound goes: "hdmi" (HDMI -> RF converter) or "analog" (3.5 mm jack,
# used with the composite cable). Set by tvout.sh in config.json.
OUTPUT=$(python3 -c "import json;print(json.load(open('config.json')).get('output','hdmi'))" 2>/dev/null || echo hdmi)
if [ "$OUTPUT" = "analog" ]; then
    SINK=$(pactl list short sinks 2>/dev/null | grep -vi hdmi | grep -i alsa | head -1 | cut -f2)
else
    SINK=$(pactl list short sinks 2>/dev/null | grep -i hdmi | head -1 | cut -f2)
fi
[ -n "$SINK" ] && pactl set-default-sink "$SINK" && pactl set-sink-volume "$SINK" 100%

exec ~/boombox-venv/bin/python player.py "$@"
