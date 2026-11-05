# Setup: Raspberry Pi + boombox

No keyboard or monitor needed: your laptop controls the Pi over Wi‑Fi (SSH), and the boombox is its screen.

> **Safety:** don't open the boombox case. The picture tube can hold a dangerous charge even when unplugged. Everything here works from the outside.

## A. Write the SD card (laptop, ~30 min)

1. Install **Raspberry Pi Imager** from raspberrypi.com/software.
2. Choose: Device **Raspberry Pi 4** → OS **Raspberry Pi OS (64‑bit)** (with desktop) → your SD card.
3. Custom settings: hostname `boombox`, a username and password, your Wi‑Fi (same as phone and laptop), time zone, keyboard, and **SSH on, with password authentication**. Leave Raspberry Pi Connect off.
4. Write the card. On a Mac, if it says *"disk not readable"* afterwards, click **Ignore**.
5. Stick the heatsinks on (biggest on the CPU), and put the Pi in its case.

## B. Wire it up (everything unplugged)

1. SD card into the Pi.
2. **Pi → modulator:** micro‑HDMI into **HDMI0** (next to the USB‑C power port) → **HDMI IN** on the HDM69.
3. **Modulator → boombox:** F coax on **RF OUT** (not ANT IN) → twin‑lead balun → crocodile clip from **one** balun wire to the bottom of the boombox's **telescopic antenna**. The second wire hangs free.
4. Modulator on. Set it with the leaflet:
   - Input switch (next to the HDMI socket) → **HDMI**
   - Channel display **57** (= UHF E21). To change the group, press **CATV/TV/AU** until **C4**, wait 2 s, then use **UP/DOWN**.
   - Sound **5.5**: press **CATV/TV/AU** until **AU**, wait 2 s, **UP/DOWN** to 5.5, wait 3 s.
   - Buttons don't react? Press **LOCK** once.
5. Boombox: **FUNCTION** fully right to **TV** (old switch: push it a few times back and forth if the screen stays dark), **TV BAND** → **UHF**, both volume sliders up.
6. Plug in the Pi's power last. Wait 2–3 minutes and tune slowly at the start of the UHF scale (near 21) until the picture appears.
7. On the back of the boombox: **BRIGHT** so black is black (not grey), **CONTRAST** to taste, **V‑HOLD** only if the picture rolls.

## C. Install the software (laptop terminal, ~15 min)

```bash
ssh <user>@boombox.local                       # "yes", then your password
echo 'export LC_ALL=C.UTF-8 LANG=C.UTF-8' >> ~/.bashrc && source ~/.bashrc   # macOS locale warnings
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git
git clone https://github.com/<you>/boombox-visuals.git
cd boombox-visuals/pi
JETSON_URL=http://jetson.local:8765 bash install.sh
sudo reboot
```

After ~1 minute the boombox shows the idle screen: a breathing ring with **BOOMBOX**.

## D. First test

```bash
ssh <user>@boombox.local
cd boombox-visuals/pi
./restart.sh --files test_music     # steady thump, circle jumps on every beat
./restart.sh                        # back to live mode
```

## E. Bluetooth from your phone

```bash
./pair.sh        # Pi is visible for 2 minutes
```

On the phone: **Settings → Bluetooth → Pair new device → Boombox**, then make sure **Media audio** is on in the device's settings. Play anything. If you paired before installing v3, **forget** the device on the phone first and pair again: the Pi now announces itself as a loudspeaker.

## F. Sync and everyday use

- The circle comes **before** the beat: `./sync.sh +20`. It comes **after** the beat: `./sync.sh -20`. Show the current value: `./sync.sh`. Reset: `./sync.sh 0`.
- Song files: copy MP3/WAV/OGG/FLAC to `~/Music/boombox`, then `./restart.sh --files`.
- Switch off gently: `sudo shutdown now`, then wait 20 s.

## G. Composite output (if the CRT doesn't lock on HDMI)

With a **3.5 mm 4‑pole → 3× RCA** cable (Raspberry Pi pinout: tip = left, ring 1 = right, ring 2 = ground, sleeve = video):

1. Cable from the Pi's audio/video jack → **yellow/red/white AV IN** on the modulator, and the modulator switch → **AV**.
2. `./tvout.sh composite`. The Pi reboots and sends native PAL 576i over the jack, sound included.
3. No picture? Try the **red** or **white** plug in the modulator's yellow input; other cables use different wiring.
4. Back to HDMI: `./tvout.sh hdmi`.

## H. Connect the Jetson

Set up the Jetson ([setup-jetson.md](setup-jetson.md)), then check from the Pi:

```bash
curl http://jetson.local:8765/health
```

If the Jetson has another name or IP, edit `pi/config.json` (`jetson_url`) and run `./restart.sh`. Captions appear a few seconds after the first sung words, and the first woodcut on the next bar line after it's painted.
