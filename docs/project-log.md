# Project log

This project was built in one long conversation between me (the maker) and **Claude** (Anthropic's AI assistant), over about a week in October–November 2026. Claude did the research, wrote all the code and docs, and walked me through the build and the debugging step by step: on my phone in the workshop, mostly in German, with photos and videos of the boombox as the main debugging tool.

Below is the story in order: what was asked, what was decided, and what went wrong. Personal details (addresses, order numbers, network names) are left out.

---

## Day 1 – 28 Oct 2026

### 1. "What is this boombox, and what did I already buy?"

I started with a screenshot of an eBay listing: a black TV boombox labelled "TVC", and the idea:

> *I want to play music through the speakers of the boombox, and the visuals should be an AI‑generated music video depending on the music that's playing.*

- Claude identified it as a mid‑80s TV/radio/cassette combo and later, from the full listing, as an **Ecotronics TVC‑4030**: German market, B/W CRT, VHF I/III + UHF IV/V, PAL B/G.
- With Gmail connected, Claude searched my recent orders and found I already had almost everything: a **Raspberry Pi 4 (8 GB) starter set**, an **HDMI‑to‑RF modulator (PAL)**, **75→300 Ω twin‑lead adapters**, sanding and cleaning supplies, and a Bambu Lab 3D printer for mounts later.
- First plan: Pi → HDMI → RF modulator → the boombox TV input. Sound and picture travel together as an analog TV signal, so the music comes out of the original speakers.

### 2. "There's nothing I bought that can generate AI video."

- Options compared: hosted music‑video services (Neural Frames, Kaiber, Freebeat) vs. building my own.
- I wanted my own. Claude sketched the pipeline (beat analysis → prompts → images → assembly).
- Then I mentioned I own an **NVIDIA Jetson Orin Nano Super**, which can run the image model locally.
- Claude recommended an NVMe SSD (Samsung 990 EVO Plus, long M.2 2280 slot) and warned that frame‑by‑frame AI video would take hours per song.

### 3. "It can max be a few seconds to a minute… could even be a circle beating to the song."

This became the core design decision:
- **Beat layer:** analyse the song and draw live: a circle pulsing on the kick drum.
- **AI layer:** a handful of images per song (SD‑Turbo, ~1–2 s each) that pulse, zoom and crossfade on the beat, instead of real AI video.

### 4. Version 1: song analysis + beating circle

- Written and tested in Claude's sandbox with a synthetic 120 BPM track.
- **Bug found in testing:** the beat tracker locked onto the hi‑hats (off‑beats). It was fixed by weighting the low‑frequency onset envelope.
- Claude also wrote a detailed step‑by‑step setup manual.

### 5. "Can we connect this to my Spotify?"

- **Version 2:** live beat detection on whatever the Pi plays. It records the output monitor with `parec` and runs bass spectral flux with an adaptive threshold. Tested at 95–170 BPM with 100 % of beats found.
- Spotify Connect via librespot/raspotify, plus the Pi as a Bluetooth speaker, plus autostart.

### 6. The real hardware

- The boombox turned out to have **no inputs at all**, so the signal goes in through the **telescopic antenna**, with a crocodile clip on one leg of the balun.
- I had no keyboard or monitor, so **v2.1** made everything run headless over SSH from my MacBook: `restart.sh`, `sync.sh`, autologin, no screen blanking, single‑instance lock.
- We flashed the SD card together in Raspberry Pi Imager 2.0 (hostname `boombox`, SSH on).

### 7. Getting a picture on a 40‑year‑old TV

A long remote‑debugging session from photos and short videos:

- The modulator display showed "57". From the leaflet's channel table, Claude worked out that this is **UHF E21** (471.25 MHz), receivable at the start of the UHF dial.
- Audio subcarrier set to **5.5 MHz** (PAL B/G).
- Several "it's broken" moments turned out to be **room reflections** on a switched‑off screen. The FUNCTION slider sat on RADIO, and its worn contacts made the TV switch on only some of the time.
- Snow and hiss finally proved the TV works. Then: **picture from the Pi + sound + the beat circle on the CRT.** 🎉

### 8. What didn't work (yet)

- **Spotify Connect:** the phone saw "Boombox", but every track was skipped. The log showed `error audio key 0 1`: Spotify has been refusing audio keys to librespot for many accounts since late 2025, and there's no fix on our side. **Bluetooth instead.**
- **Bluetooth:** the phone connected, but `wpctl status` showed no audio source. The Pi wasn't announced as a speaker, so the installer now sets the Bluetooth class to loudspeaker, and the phone needs a re‑pair.
- **Picture lock:** the CRT doesn't lock horizontally on the modulator's HDMI‑derived signal. The result is a shifted image with a bright band on the left and a vertical seam, on every channel. We tried Video/RF level, BRIGHT/CONTRAST/V‑HOLD (there's no H‑HOLD on this set), and HDMI modes 720×576@50 (no picture at all, reverted) and 1280×720@50 (no change).
  → Next step: the Pi's **native composite PAL output** with a 4‑pole 3.5 mm → RCA cable into the modulator's AV input (`tvout.sh`).
- **My own bug, found by Claude:** `restart.sh` matched the wrong process name, so the autostarted player kept running and the test never started. Fixed.

## 2–5 Nov 2026

### 9. Concept video and technical description

Short paragraphs for generating a concept video, plus an exact technical description of the system ([how-it-works.md](how-it-works.md)).

### 10. "The images should be based on the lyrics. Use Whisper."

**Version 3**, this repository:
- **Jetson dream server:** Whisper (lyrics, translated to English) → prompt builder (keywords + mood from tempo and loudness + a B/W CRT style) → SD‑Turbo, 1 step. Every image is saved with its lyrics for a gallery.
- **Pi:** keeps the last 15 s of audio and uploads 8 s every 10 s while music plays. Images are converted to high‑contrast greyscale, crossfaded, and zoom and flash on the beat, with the lyric line underneath.
- **Mock mode** so the whole chain can be tested without a GPU. It was tested end to end: beat circle first, then four images received and rendered with crossfades.
- `tvout.sh` for the composite route, a config file, and docs.

### 11. "No, how it works is…"

I described the actual vision:

> *It runs live speech‑to‑text Whisper on whatever song is streamed over Bluetooth, transcribes the vocal line in real time as blocky 1980s European PAL text titles, and generates a high‑contrast graphic noir woodcut scene illustrating the literal words being sung, cutting on music bar lines.*

So the AI part was rebuilt around it:
- The Jetson server split into **`/hear`** (fast Whisper, every 2 s) and **`/paint`** (SD‑Turbo, once per *new* line). Whisper now transcribes the sung language as it is, with translation optional.
- The prompt is the **literal sung line** plus a fixed noir‑woodcut style, with no more keyword‑and‑mood mixing.
- **Teletext captions** on the Pi: tiny bold monospace without antialiasing, blown up into double‑height pixel letters on black boxes.
- **Bar‑line cuts:** a finished picture waits for the next downbeat and hard‑cuts in. The images are posterised to 4 flat tones, like a print.
- Mock test: every cut landed on a downbeat (beats 4, 20, 28, 44; 0–80 ms after the beat), each line was painted once, and captions appeared before the picture.

---

## Lessons learned

- **Check the old hardware first.** Inputs, TV system and power decide the whole design, and a 1980s portable TV may have no inputs at all.
- **Photos and short videos are the best remote debugging tool,** even for audio (I could check silence vs. hiss from the video's sound track).
- **Old slide switches lie.** If a vintage device "suddenly" stops working, wiggle the switch before suspecting the electronics.
- **Spotify Connect clones are fragile.** Bluetooth is the boring option that works with any app.
- **Plan the AI around the hardware.** A few seconds of compute per image, synced to beats, feels alive; full AI video on an 8 GB board doesn't fit a live show.
