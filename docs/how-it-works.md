# How it works

## Signal chain

```
Phone ──Bluetooth A2DP──► Raspberry Pi 4 ──HDMI──► HDM69 modulator ──RF (PAL B/G, UHF ch. 21, 471.25 MHz)──►
      coax ──► 75→300 Ω balun ──► crocodile clip on the telescopic antenna ──► Ecotronics TVC‑4030 (CRT + speakers)

Raspberry Pi ◄──HTTP (LAN)──► Jetson Orin Nano Super   (/hear: 5 s WAV up, text down · /paint: line up, PNG down)
```

- Picture and sound share one analog TV signal. The boombox's own tuner demodulates it, so the audio is mono and plays through the original speakers.
- The boombox has **no inputs**. The RF signal is coupled into the telescopic antenna through one leg of a twin‑lead balun, which is plenty at a distance of a few centimetres.
- Modulator settings: PAL, audio subcarrier **5.5 MHz** (B/G, Switzerland/Germany), channel display **57** = UHF E21. Channel 72 = UHF E36 also works.

## Raspberry Pi (`pi/`)

| File | Role |
| --- | --- |
| `live.py` | Records the Pi's own output (`parec` on the default sink's monitor, 44.1 kHz mono) and detects beats live. Also keeps the last 15 s of audio for the Jetson. |
| `player.py` | pygame renderer, 720×576 logical resolution (PAL), scaled to the real output, 50 fps. Teletext captions, woodcut layer with bar‑line cuts, beat circle, idle screen. |
| `dream.py` | Two background threads. **Listener:** every `hear_every_seconds` (2 s) sends the last `hear_window_seconds` (5 s) of audio to `/hear` and keeps the newest sung line. **Painter:** for each *new* line (less than 50 % word overlap with the last painted one) asks `/paint` for a picture. |
| `run.sh` / `restart.sh` | Picks the audio sink (HDMI or analog), starts the player; restart works over SSH. |
| `pair.sh` | 2‑minute Bluetooth pairing window, accepts without PIN, trusts the phone. |
| `sync.sh` | Shifts the visuals against the sound (CRT/modulator delay), saved in `~/.boombox_delay`. |
| `tvout.sh` | Switches the picture between HDMI and the Pi's composite PAL output. |
| `install.sh` | Packages, venv, Bluetooth loudspeaker class (`0x200414`), autologin, no screen blanking, autostart. |

### Beat detection

Every hop of 512 samples (~11.6 ms):

1. Hann‑windowed 1024‑point FFT. Sum the 35–160 Hz bins (kick drum and bass).
2. Onset strength = positive change of `log(1 + bass energy)` (spectral flux).
3. A beat fires when the flux is above **mean + 1.5 × std** of the last 1.5 s, at least 0.15, and at least 0.28 s after the previous beat (max ~214 BPM).
4. Automatic gain: bass and loudness are relative to slowly decaying peaks. Silence (RMS < 0.003 for 2.5 s) shows the idle screen.
5. Tempo = 60 / median gap of the last beats. Every 4th beat counts as the downbeat.

On synthetic test tracks (95–170 BPM, kick + snare + hi‑hat + bass line, also at 30 % volume) it found 100 % of the beats with about 0–2 ms latency.

### Visuals

- **Beat circle:** a white disc whose radius follows the bass plus a beat pulse `e^(−7t)`. Up to three rings expand from recent beats, and the downbeat gets a stronger pulse and a background flash. Everything stays inside the middle 80 % of the picture because old CRTs cut off the edges (overscan).
- **Teletext captions:** the newest sung line, wrapped to 32 columns and shown as the last two rows. Each row is drawn in a tiny bold monospace font without antialiasing, then scaled up with hard pixels at double height on a black box, like 1980s European teletext subtitles.
- **Woodcut layer:** the Jetson's picture is converted to greyscale, contrast‑stretched (3rd–97th percentile), given an S‑curve for deeper blacks and posterised to `woodcut_levels` flat tones (default 4), like a print.
- **Cutting on bar lines:** a new picture waits as *pending* and is swapped in with a hard cut on the next downbeat (every 4th detected beat), or after 2.5 s without any beat (breaks, ballads). Each beat gives a small punch‑in: 2.5 %, or 5 % on the downbeat.
- After 10 s of silence the pictures are cleared and the next song starts fresh.

## Jetson (`jetson/`)

`server.py` is a plain HTTP server (Python standard library) on port 8765.

| Endpoint | |
| --- | --- |
| `GET /health` | `{"ok": true, "mode": "ai"/"mock", "ears": "...", "heard": n, "painted": n}` |
| `POST /hear` | body = WAV (16‑bit) → `{"text": "<vocal line>", "ms": 420}` |
| `POST /paint` | body = `{"line": "..."}` → PNG; header `X-Prompt` (URL‑encoded) |

One model runs on the GPU at a time (a lock), so a caption may wait for a painting already in progress (≤ ~2 s).

1. **Whisper** (`small` by default). It tries faster‑whisper on the GPU, then openai‑whisper on the GPU, then faster‑whisper on the CPU (int8). It runs with VAD filtering and no conditioning on previous text, against hallucinations. By default it **transcribes** the sung language as it is. `--translate` gives English captions and prompts instead.
2. **Cleaning:** drops Whisper's typical music hallucinations ("thanks for watching", "[Music]", one word repeated, …) and filler ("oh", "yeah", "na na").
3. **Prompt:** the literal line, *"illustration of the words: '<line>'"*, plus the style *"high contrast graphic noir woodcut print, bold black ink on white paper, linocut carving marks, dramatic chiaroscuro, film noir, stark, no text"*. No keywords, no language model: the sung words are the subject.
4. **SD‑Turbo** (`stabilityai/sd-turbo`, fp16, 1 step, guidance 0, 512 × 512, attention slicing, random seed).
5. With `--save-gallery`, every picture is saved with its line and prompt in `jetson/gallery/`.

`--mock` replaces Whisper with a fake song (a new line every 6 s) and SD‑Turbo with drawn placeholder woodcuts, so the whole chain can be tested on any computer.

**Latency:** the caption appears ~2–3 s after the words are sung (2 s listening interval, up to 5 s window, Whisper time). The picture follows on the next downbeat after it's painted.

## Why these choices

- **Live analysis instead of pre‑analysed files:** streamed music can't be analysed in advance, and live analysis also works for any app over Bluetooth.
- **One picture per sung line instead of AI video:** an AI video model on an 8 GB Jetson would take hours per song. One SD‑Turbo step takes ~1–2 s, fast enough to illustrate each line, and hard cuts on bar lines give it the rhythm of an edited music video.
- **Noir woodcut and teletext:** the boombox CRT is monochrome and tiny. Bold black‑and‑white shapes and chunky letters survive it, while fine detail and colour don't. Both also fit the 1980s European TV look.
- **HTTP with WAV/PNG:** no extra dependencies and easy to test with `curl`. If the Jetson is off, the Pi doesn't care.
