#!/bin/bash
# Shift the visuals against the music, no keyboard needed.
#   ./sync.sh +20    circle 20 ms later   (use when the circle comes BEFORE the beat)
#   ./sync.sh -20    circle 20 ms earlier (use when the circle comes AFTER the beat)
#   ./sync.sh 0      back to no delay
#   ./sync.sh        show the current value
F=~/.boombox_delay
cur=$(cat "$F" 2>/dev/null || echo 0)
if [ -z "$1" ]; then
    echo "Current delay: $(python3 -c "print(round($cur*1000))") ms"
    exit 0
fi
case "$1" in
    +*|-*) new=$(python3 -c "print(max(0.0, $cur + $1/1000))") ;;
    *)     new=$(python3 -c "print(max(0.0, $1/1000))") ;;
esac
printf '%.3f' "$new" > "$F"
echo "Delay now: $(python3 -c "print(round($new*1000))") ms (the boombox screen shows it for 3 seconds)"
