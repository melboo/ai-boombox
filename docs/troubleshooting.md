# Troubleshooting

| What you see | Likely cause | Try this |
| --- | --- | --- |
| `ssh: Could not resolve hostname boombox.local` | Pi still booting, or laptop on another network | Wait 2–3 min; same Wi‑Fi; re‑write the SD card with the right Wi‑Fi details |
| Lots of `setlocale: LC_CTYPE` warnings over SSH | macOS sends its locale | `echo 'export LC_ALL=C.UTF-8 LANG=C.UTF-8' >> ~/.bashrc` (harmless anyway) |
| Boombox screen dark, only room reflections, no hiss | TV section not switched on | Push **FUNCTION** fully to **TV**; worn contacts: slide back and forth 10×, or contact spray (unplugged) |
| Only snow and hiss | Mistuned, wrong channel, or cable on ANT IN | Cable on **RF OUT**; modulator on **57**; tune near 21 at the start of the UHF scale |
| Grey screen with a flickering vertical line, no sound | Modulator gets no picture from the Pi | Undo HDMI mode tweaks in `/boot/firmware/cmdline.txt` (`video=...`), reboot |
| Picture but no sound | Wrong audio subcarrier | Modulator **AU → 5.5** (PAL B/G) |
| Everything grey, circle barely visible | Brightness too high | **BRIGHT** down until black is black; modulator **Video Adj.** counter‑clockwise = more contrast |
| Bright band on the left, picture shifted, vertical seam | CRT doesn't lock horizontally on the modulator's HDMI‑derived signal (no H‑HOLD on this set) | Composite output: `./tvout.sh composite` + 4‑pole AV cable ([setup‑pi.md](setup-pi.md#g-composite-output-if-the-crt-doesnt-lock-on-hdmi)) |
| `./restart.sh --files test_music` plays nothing | An older player is still running | `pkill -f "python player.py"; ./restart.sh --files test_music` |
| `Boombox Visuals is already running.` in `/tmp/boombox.log` | Same as above | Same as above |
| Phone connected via Bluetooth but silent | Phone doesn't send media audio | `wpctl status` → no Bluetooth source? Forget **Boombox** on the phone, `./pair.sh`, pair again, turn **Media audio** on |
| Bluetooth: Boombox not in the phone's list | Pairing window closed / Bluetooth blocked | `sudo rfkill unblock bluetooth`, `./pair.sh`, refresh the phone's list right away |
| Spotify "Boombox" device skips every song | Spotify refuses librespot audio keys | Not fixable on our side; use Bluetooth ([librespot#1664](https://github.com/librespot-org/librespot/issues/1664)) |
| No captions, no pictures | Jetson not reachable | On the Pi: `curl http://jetson.local:8765/health`; check `jetson_url` in `pi/config.json`; on the Jetson: `journalctl -u boombox-dream -f` |
| Captions wrong or nonsense | Whisper mishears dense mixes | Try `--whisper medium`, or `--language en/de` on the Jetson |
| Pictures change mid‑bar | Beat detector missed the downbeat (or no beat for 2.5 s) | Normal in breaks; songs with a clear kick drum cut cleanly |
| Captions run a few seconds behind | Listening window + Whisper time | Lower `hear_window_seconds` to 3–4 in `pi/config.json` (less context, faster) |
| Circle early or late | Modulator/CRT delay | `./sync.sh +20` / `./sync.sh -20` |
