#!/usr/bin/env python3
"""
Boombox Visuals - talks to the Jetson "dream server".

Two background threads:
  Listener  every ~2 s, sends the last ~5 s of the song to /hear. Whisper on
            the Jetson writes down the vocal line -> live teletext captions.
  Painter   whenever a *new* line is sung, asks /paint for a noir woodcut of
            those literal words. The player cuts to it on the next bar line.

If the Jetson is off or unreachable nothing breaks: no captions, no images,
the beat circle keeps going, and this keeps trying quietly.
"""
import io
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import wave

import numpy as np

UPLOAD_RATE = 16000        # Whisper works at 16 kHz; smaller upload


def to_wav(audio, rate):
    """float32 mono -> 16-bit WAV bytes at 16 kHz."""
    if rate != UPLOAD_RATE and len(audio):
        n = int(len(audio) * UPLOAD_RATE / rate)
        audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio)
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(UPLOAD_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def words_of(line):
    return set(w.strip("'") for w in line.lower().split() if w.strip(".,!?'\""))


def is_new_line(line, previous):
    """A different lyric line, not the same one heard again in the next window."""
    a, b = words_of(line), words_of(previous or "")
    if not a:
        return False
    if not b:
        return True
    return len(a & b) / len(a | b) < 0.5


class DreamClient:
    def __init__(self, detector, url, hear_every=2.0, hear_window=5.0, timeout=30.0):
        self.detector = detector
        self.url = url.rstrip("/")
        self.hear_every, self.hear_window, self.timeout = hear_every, hear_window, timeout
        self.lock = threading.Lock()
        self.caption = ""             # latest sung line (for the teletext captions)
        self.caption_at = 0.0         # when it was heard (time.monotonic)
        self.latest_image = None      # (png_bytes, line), taken by the player
        self.online = False
        self._painted_line = ""
        self._paint_wanted = None
        self._wake_painter = threading.Event()

    def start(self):
        threading.Thread(target=self._listen_loop, daemon=True).start()
        threading.Thread(target=self._paint_loop, daemon=True).start()

    # -- for the player
    def take_image(self):
        with self.lock:
            item, self.latest_image = self.latest_image, None
        return item

    def current_caption(self, now, hold=6.0):
        with self.lock:
            if self.caption and now - self.caption_at < hold:
                return self.caption
        return ""

    def new_song(self):
        with self.lock:
            self.caption = ""
            self._painted_line = ""

    # -- background work
    def _post(self, path, data, content_type):
        req = urllib.request.Request(self.url + path, data=data,
                                     headers={"Content-Type": content_type}, method="POST")
        return urllib.request.urlopen(req, timeout=self.timeout)

    def _listen_loop(self):
        was_active = False
        while True:
            t0 = time.monotonic()
            s = self.detector.state(t0)
            if not s["active"]:
                if was_active:
                    self.new_song()
                was_active = False
                time.sleep(0.5)
                continue
            was_active = True
            audio = self.detector.recent_audio(self.hear_window)
            if len(audio) >= self.detector.rate:
                try:
                    with self._post("/hear", to_wav(audio, self.detector.rate), "audio/wav") as r:
                        text = json.loads(r.read()).get("text", "").strip()
                    self.online = True
                    if text:
                        with self.lock:
                            self.caption, self.caption_at = text, time.monotonic()
                            wanted = is_new_line(text, self._painted_line)
                        if wanted:
                            self._paint_wanted = text
                            self._wake_painter.set()
                except (urllib.error.URLError, OSError, ValueError) as e:
                    if self.online:
                        print(f"[dream] Jetson unreachable: {e}", flush=True)
                    self.online = False
                    time.sleep(5)
            time.sleep(max(0.0, self.hear_every - (time.monotonic() - t0)))

    def _paint_loop(self):
        while True:
            self._wake_painter.wait()
            self._wake_painter.clear()
            line = self._paint_wanted
            if not line:
                continue
            try:
                body = json.dumps({"line": line}).encode()
                with self._post("/paint", body, "application/json") as r:
                    png = r.read()
                with self.lock:
                    self.latest_image = (png, line)
                    self._painted_line = line
            except (urllib.error.URLError, OSError, ValueError) as e:
                print(f"[dream] paint failed: {e}", flush=True)
                time.sleep(2)
