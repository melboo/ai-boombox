#!/usr/bin/env python3
"""
Boombox Visuals v3 - player (runs on the Raspberry Pi)

Shows visuals that beat along with whatever the Pi is playing (Bluetooth
from your phone, or song files). With the Jetson dream server reachable:
  - the sung line appears live as blocky 1980s teletext subtitles,
  - a high-contrast noir woodcut of those literal words fills the screen,
    cutting to each new picture on the next bar line (downbeat).
Without the Jetson: the beat circle.

Usage:
    ./run.sh                     live mode (Bluetooth)
    ./run.sh --files             also play the songs in ~/Music/boombox
    ./run.sh --files /some/dir   play the songs in another folder
    ./run.sh --windowed          in a window, for testing on a monitor
    ./run.sh --no-dream          never contact the Jetson

Settings: config.json next to this file (copied from config.example.json).

Keys:
    + / -          visuals later / earlier (fix sync), 10 ms steps
    Right arrow/N  next song (file mode)
    Esc / Q        quit
"""
import argparse
import fcntl
import io
import json
import math
import os
import time

import numpy as np
import pygame

from dream import DreamClient
from live import BeatDetector, Capture

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(HERE, "config.json")
DEFAULT_CONFIG = {
    "jetson_url": "http://jetson.local:8765",
    "hear_every_seconds": 2,
    "hear_window_seconds": 5,
    "show_captions": True,
    "woodcut_levels": 4,
    "output": "hdmi",
}
DEFAULT_MUSIC = os.path.expanduser("~/Music/boombox")
DELAY_FILE = os.path.expanduser("~/.boombox_delay")
AUDIO_EXT = (".mp3", ".wav", ".ogg", ".flac")
FPS = 50                 # matches PAL TV (50 Hz)
SCREEN = (720, 576)      # PAL picture size; scaled to the real output by SDL
SAFE_AREA = 0.80         # old CRTs cut off the edges; keep everything in the middle 80%
CUT_FALLBACK = 2.5       # no beat for this long: cut to a new image anyway


# ---------------------------------------------------------------- settings
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE) as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def load_delay():
    try:
        with open(DELAY_FILE) as f:
            return max(0.0, float(f.read().strip()))
    except (OSError, ValueError):
        return 0.0


def save_delay(v):
    try:
        with open(DELAY_FILE, "w") as f:
            f.write(f"{v:.3f}")
    except OSError:
        pass


def find_songs(folder):
    if not os.path.isdir(folder):
        return []
    return sorted(
        os.path.join(folder, f) for f in os.listdir(folder)
        if f.lower().endswith(AUDIO_EXT) and not f.startswith(".")
    )


# ---------------------------------------------------------------- drawing
def pulse_of(s):
    return math.exp(-s["since"] * 7.0)      # 1 right on the beat, fades fast


class BeatCircle:
    """A pulsing circle plus rings that spread out on each beat."""

    def __init__(self, size):
        self.w, self.h = size
        self.cx, self.cy = self.w // 2, self.h // 2
        self.max_r = min(self.w, self.h) * SAFE_AREA / 2

    def rings(self, surf, s, strength=1.0):
        for age in s["ring_ages"]:
            if age > 1.2:
                continue
            r = self.max_r * (0.35 + age * 0.9)
            if r > self.max_r:
                continue
            fade = max(0.0, 1.0 - age / 1.2) * strength
            c = int(220 * fade)
            pygame.draw.circle(surf, (c, c, c), (self.cx, self.cy), int(r), max(3, int(10 * fade)))

    def draw(self, surf, s):
        pulse = pulse_of(s)
        strong = s["strong"]
        flash = int(45 * pulse) if strong else int(15 * pulse)
        surf.fill((flash, flash, flash))
        self.rings(surf, s)
        boost = 0.45 if strong else 0.30
        r = min(self.max_r, self.max_r * (0.30 + 0.20 * s["bass"] + boost * pulse))
        b = int(120 + 135 * max(s["loud"], pulse))
        pygame.draw.circle(surf, (b, b, b), (self.cx, self.cy), int(r))
        pygame.draw.circle(surf, (0, 0, 0), (self.cx, self.cy), int(r * 0.25))


class WoodcutLayer:
    """The AI pictures: stark black and white, swapped with a hard cut on the bar line."""

    def __init__(self, size, levels=4):
        self.w, self.h = size
        self.side = self.h                      # square images, full height
        self.levels = levels
        self.current = None
        self.pending = None
        self.last_beat_seen = -1

    def prepare(self, png_bytes):
        """PNG from the Jetson -> grey, contrast-stretched, posterised like a print."""
        img = pygame.image.load(io.BytesIO(png_bytes), "dream.png")
        img = pygame.transform.smoothscale(img, (self.side, self.side))
        rgb = pygame.surfarray.array3d(img).astype(np.float32)
        grey = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
        lo, hi = np.percentile(grey, 3), np.percentile(grey, 97)
        grey = np.clip((grey - lo) / max(1.0, hi - lo), 0, 1)
        grey = grey * grey * (3 - 2 * grey)                     # S-curve: deeper blacks
        if self.levels and self.levels >= 2:                    # few flat tones = woodcut
            grey = np.round(grey * (self.levels - 1)) / (self.levels - 1)
        g = (grey * 255).astype(np.uint8)
        return pygame.surfarray.make_surface(np.stack([g, g, g], axis=-1))

    def offer(self, png_bytes):
        self.pending = self.prepare(png_bytes)

    def clear(self):
        self.current = self.pending = None

    @property
    def active(self):
        return self.current is not None

    def update(self, s):
        """Cut to the waiting picture on the first beat of a bar."""
        if self.pending is None:
            self.last_beat_seen = s["beat_n"]
            return
        new_beat = s["beat_n"] != self.last_beat_seen
        self.last_beat_seen = s["beat_n"]
        if self.current is None or (new_beat and s["strong"]) or s["since"] > CUT_FALLBACK:
            self.current, self.pending = self.pending, None

    def draw(self, screen, s):
        pulse = pulse_of(s)
        zoom = 1.0 + (0.05 if s["strong"] else 0.025) * pulse     # small punch on the beat
        side = int(self.side * zoom)
        z = pygame.transform.scale(self.current, (side, side))
        screen.fill((0, 0, 0))
        screen.blit(z, ((self.w - side) // 2, (self.h - side) // 2))


class Teletext:
    """Subtitles the way 1980s European TV did them: chunky pixel letters in black boxes."""

    COLS = 32                                   # characters per row (teletext had 40)

    def __init__(self, size):
        self.w, self.h = size
        self.scale = max(2, self.w // (self.COLS * 8))
        try:
            self.font = pygame.font.SysFont("dejavusansmono,liberationmono,monospace", 10, bold=True)
        except Exception:
            self.font = pygame.font.Font(None, 14)

    def wrap(self, text):
        rows, row = [], ""
        for word in text.split():
            if len(row) + len(word) + 1 > self.COLS:
                rows.append(row)
                row = word
            else:
                row = f"{row} {word}".strip()
        if row:
            rows.append(row)
        return rows[-2:]                        # newest two rows, like rolling subtitles

    def row_surface(self, text):
        # No antialiasing at a tiny size, then blown up with hard pixels: blocky letters
        small = self.font.render(" " + text + " ", False, (255, 255, 255), (0, 0, 0))
        w, h = small.get_size()
        return pygame.transform.scale(small, (w * self.scale, h * self.scale * 2))   # double height

    def draw(self, screen, text):
        if not text:
            return
        rows = [self.row_surface(r) for r in self.wrap(text)]
        y = int(self.h * 0.90)
        for surf in reversed(rows):
            y -= surf.get_height()
            screen.blit(surf, ((self.w - surf.get_width()) // 2, y))


def draw_idle(surf, font, now):
    """Shown when nothing is playing: a slowly breathing ring and how to connect."""
    surf.fill((0, 0, 0))
    w, h = surf.get_size()
    breathe = 0.5 + 0.5 * math.sin(now * 1.6)
    r = int(min(w, h) * SAFE_AREA / 2 * (0.42 + 0.05 * breathe))
    c = int(90 + 80 * breathe)
    pygame.draw.circle(surf, (c, c, c), (w // 2, int(h * 0.42)), r, 6)
    draw_text(surf, font, "BOOMBOX", int(h * 0.42) - font.get_height() // 2)
    draw_text(surf, font, "Bluetooth: choose 'Boombox'", int(h * 0.72))


def draw_text(surf, font, text, y, alpha=255, backing=True):
    if not text:
        return
    img = font.render(text, True, (255, 255, 255))
    if img.get_width() > surf.get_width() * SAFE_AREA:      # too long: shorten
        while text and font.size(text + "...")[0] > surf.get_width() * SAFE_AREA:
            text = text[:-1]
        img = font.render(text + "...", True, (255, 255, 255))
    x = (surf.get_width() - img.get_width()) // 2
    if backing:   # dark box behind the words so they stay readable
        box = pygame.Surface((img.get_width() + 16, img.get_height() + 6))
        box.fill((0, 0, 0))
        box.set_alpha(int(alpha * 0.8))
        surf.blit(box, (x - 8, y - 3))
    img.set_alpha(alpha)
    surf.blit(img, (x, y))


# ---------------------------------------------------------------- file playback
class FilePlayer:
    """Plays the songs in a folder one after another, on repeat."""

    def __init__(self, folder):
        self.folder = folder
        self.queue = []
        pygame.mixer.init(44100, -16, 2, 2048)

    def update(self):
        """Start the next song when nothing is playing. Returns a new title or None."""
        if pygame.mixer.music.get_busy():
            return None
        return self.next()

    def next(self):
        if not self.queue:
            self.queue = find_songs(self.folder)
            if not self.queue:
                return None
        path = self.queue.pop(0)
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
        except pygame.error as e:
            print(f"Skipping {path}: {e}")
            return None
        return os.path.splitext(os.path.basename(path))[0]


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Boombox Visuals v3")
    ap.add_argument("--files", nargs="?", const=DEFAULT_MUSIC, default=None,
                    metavar="FOLDER", help="also play song files (default ~/Music/boombox)")
    ap.add_argument("--windowed", action="store_true", help="run in a window (testing)")
    ap.add_argument("--no-dream", action="store_true", help="don't use the Jetson")
    ap.add_argument("--jetson", default=None, help="dream server URL (overrides config.json)")
    ap.add_argument("--record", default=None, metavar="DIR",
                    help="save one frame per second as PNG (for testing)")
    args = ap.parse_args()
    cfg = load_config()

    # Only one copy may run (autostart can fire twice)
    global _lock
    _lock = open(os.path.expanduser("~/.boombox_player.lock"), "w")
    try:
        fcntl.flock(_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Boombox Visuals is already running.")
        return

    pygame.display.init()
    pygame.font.init()
    if args.windowed:
        screen = pygame.display.set_mode(SCREEN)
    else:
        screen = pygame.display.set_mode(SCREEN, pygame.FULLSCREEN | pygame.SCALED)
        pygame.mouse.set_visible(False)
    pygame.display.set_caption("Boombox Visuals")

    clock = pygame.time.Clock()
    font = pygame.font.Font(None, SCREEN[1] // 14)
    circle = BeatCircle(SCREEN)
    layer = WoodcutLayer(SCREEN, levels=int(cfg.get("woodcut_levels", 4)))
    teletext = Teletext(SCREEN)

    detector = BeatDetector()
    capture = Capture(detector)
    capture.start()

    dream = None
    if not args.no_dream:
        url = args.jetson or cfg["jetson_url"]
        dream = DreamClient(detector, url, hear_every=float(cfg["hear_every_seconds"]),
                            hear_window=float(cfg["hear_window_seconds"]))
        dream.start()
        print(f"Dream server: {url}", flush=True)

    files = FilePlayer(args.files) if args.files else None
    delay = load_delay()
    delay_shown_until = 0.0
    title, title_until = "", 0.0
    checked = 0.0
    silent_since = None
    next_record = 0.0
    if args.record:
        os.makedirs(args.record, exist_ok=True)

    while True:
        now = time.monotonic()

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return
            if ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_ESCAPE, pygame.K_q):
                    return
                if ev.key in (pygame.K_RIGHT, pygame.K_n) and files:
                    pygame.mixer.music.stop()
                if ev.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    delay = delay + 0.01
                    save_delay(delay)
                    delay_shown_until = now + 2
                if ev.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    delay = max(0.0, delay - 0.01)
                    save_delay(delay)
                    delay_shown_until = now + 2

        if files:
            new = files.update()
            if new:
                title, title_until = new, now + 5
        if now - checked > 1:
            checked = now
            new_delay = load_delay()           # sync.sh may have changed it
            if abs(new_delay - delay) > 1e-6:
                delay = new_delay
                delay_shown_until = now + 3

        # New picture from the Jetson? It waits for the next bar line.
        if dream:
            item = dream.take_image()
            if item:
                try:
                    layer.offer(item[0])
                except (pygame.error, ValueError) as e:
                    print(f"[dream] bad image: {e}", flush=True)

        s = detector.state(now, delay)
        if s["active"]:
            silent_since = None
            layer.update(s)
            if layer.active:
                layer.draw(screen, s)
            else:
                circle.draw(screen, s)
            if now < title_until:
                alpha = int(255 * min(1.0, title_until - now))
                draw_text(screen, font, title, int(SCREEN[1] * 0.10), alpha)
            if dream and cfg.get("show_captions", True):
                teletext.draw(screen, dream.current_caption(now))
        else:
            if silent_since is None:
                silent_since = now
            if now - silent_since > 10 and layer.active:   # song over: start fresh
                layer.clear()
            draw_idle(screen, font, now)
        if capture.error:
            draw_text(screen, font, capture.error, int(SCREEN[1] * 0.88))
        if now < delay_shown_until:
            draw_text(screen, font, f"delay {delay * 1000:.0f} ms", int(SCREEN[1] * 0.88))

        pygame.display.flip()
        if args.record and now >= next_record:
            next_record = now + 1.0
            pygame.image.save(screen, os.path.join(args.record, f"frame_{int(now * 10):08d}.png"))
        clock.tick(FPS)


if __name__ == "__main__":
    try:
        main()
    finally:
        pygame.quit()
