#!/bin/bash
# Makes the Pi visible as "Boombox" for 2 minutes so your phone can pair with it.
# Run:  ./pair.sh   then pick "Boombox" in your phone's Bluetooth settings.

echo "Bluetooth pairing mode for 2 minutes. On your phone: Settings > Bluetooth > Boombox"
bluetoothctl power on >/dev/null
bluetoothctl system-alias Boombox >/dev/null
bluetoothctl pairable on >/dev/null
bluetoothctl discoverable on >/dev/null

# Accept pairing without a PIN
bt-agent -c NoInputNoOutput >/dev/null 2>&1 &
AGENT=$!

# Trust every paired phone so it reconnects by itself next time
for i in $(seq 1 24); do
    for mac in $(bluetoothctl devices Paired | awk '{print $2}'); do
        bluetoothctl trust "$mac" >/dev/null
    done
    sleep 5
done

kill "$AGENT" 2>/dev/null
bluetoothctl discoverable off >/dev/null
echo "Pairing mode off. Paired devices:"
bluetoothctl devices Paired
