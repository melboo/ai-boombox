#!/usr/bin/env python3
"""
Boombox Dream Server - runs on the NVIDIA Jetson.

Two jobs, both asked for by the Raspberry Pi:

  /hear   The Pi sends the last few seconds of the song every ~2 s.
          Whisper writes down the vocal line it hears -> live teletext captions.
  /paint  For every new sung line, the Pi asks for a picture. SD-Turbo paints
          a high-contrast noir woodcut of the literal words (one diffusion
          step, ~1-2 s on Orin Nano). The Pi cuts to it on the next bar line.

Usage:
    python3 server.py                 real models (needs GPU + model download)
    python3 server.py --mock          no AI: fake lyrics + drawn images (testing)
    python3 server.py --whisper small --save-gallery

Endpoints:
    GET  /health  -> {"ok": true, "mode": "...", ...}
    POST /hear    body: WAV (any rate, 16-bit)      -> {"text": "...", "ms": 412}
    POST /paint   body: {"line": "..."} (JSON)      -> PNG; header X-Prompt (URL-encoded)
"""
import argparse
import io
import json
import os
import random
import sys
import threading
import time
import urllib.parse
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

from prompts import DEFAULT_STYLE, PromptBuilder, clean_lyrics

HERE = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------ audio
def read_wav(data):
    """WAV bytes -> float32 mono at 16 kHz (what Whisper wants)."""
    with wave.open(io.BytesIO(data)) as w:
        rate, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError("WAV must be 16-bit")
    a = np.frombuffer(raw, "<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    if rate != 16000 and len(a):
        n = int(len(a) * 16000 / rate)
        a = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)
    return a


# ------------------------------------------------------------------ hearing
class Ears:
    """Whisper speech-to-text. Tries faster-whisper (GPU), openai-whisper (GPU), faster-whisper (CPU)."""

    def __init__(self, size="small", language=None, translate=False):
        self.language = language
        # Default: write down the words as sung (captions show the real lyrics).
        # --translate: English output whatever the language (best for the image model).
        self.task = "translate" if translate else "transcribe"
        self.kind = None
        errors = []
        try:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(size, device="cuda", compute_type="float16")
            self.kind = "faster-whisper (GPU)"
        except Exception as e:
            errors.append(f"faster-whisper GPU: {e}")
        if self.kind is None:
            try:
                import torch
                import whisper  # openai-whisper
                if not torch.cuda.is_available():
                    raise RuntimeError("no CUDA")
                self.model = whisper.load_model(size, device="cuda")
                self.kind = "openai-whisper (GPU)"
            except Exception as e:
                errors.append(f"openai-whisper GPU: {e}")
        if self.kind is None:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(size, device="cpu", compute_type="int8")
            self.kind = "faster-whisper (CPU)"
            for err in errors:
                print(f"[ears] skipped {err}", flush=True)
        print(f"[ears] {self.kind}, model '{size}', {self.task}", flush=True)

    def hear(self, audio16k):
        if len(audio16k) < 16000:            # under 1 second: nothing to hear
            return ""
        if self.kind.startswith("faster"):
            segs, _ = self.model.transcribe(
                audio16k, language=self.language, task=self.task, vad_filter=True,
                beam_size=1, condition_on_previous_text=False,
            )
            return " ".join(s.text for s in segs).strip()
        r = self.model.transcribe(audio16k, language=self.language, task=self.task,
                                  fp16=True, condition_on_previous_text=False)
        return r.get("text", "").strip()


# ------------------------------------------------------------------ painting
class Painter:
    """SD-Turbo text-to-image: one step, no guidance, 512x512."""

    def __init__(self, model_id="stabilityai/sd-turbo", steps=1, size=512):
        import torch
        from diffusers import AutoPipelineForText2Image
        self.torch = torch
        self.steps, self.size = steps, size
        self.pipe = AutoPipelineForText2Image.from_pretrained(
            model_id, torch_dtype=torch.float16, variant="fp16")
        self.pipe.to("cuda")
        self.pipe.set_progress_bar_config(disable=True)
        try:
            self.pipe.enable_attention_slicing()       # less memory on 8 GB
        except Exception:
            pass
        print(f"[painter] {model_id}, {steps} step(s), {size}px", flush=True)
        self.paint("warm up")                          # first image is slow; do it now

    def paint(self, prompt):
        g = self.torch.Generator("cuda").manual_seed(random.randint(0, 2**31 - 1))
        return self.pipe(prompt=prompt, num_inference_steps=self.steps, guidance_scale=0.0,
                         width=self.size, height=self.size, generator=g).images[0]


# ------------------------------------------------------------------ mock mode
MOCK_SONG = [
    "I walk alone down the empty street",
    "the city lights are burning in the rain",
    "a black cat crossing the railway line",
    "your shadow dancing on the wall",
    "the last train leaves at midnight",
    "and the moon is hanging over the harbour",
]


class MockEars:
    """Pretends a song is playing: a new line every 6 seconds."""
    kind = "mock"

    def hear(self, audio16k):
        return MOCK_SONG[int(time.time() // 6) % len(MOCK_SONG)]


class MockPainter:
    """Draws a stark black-and-white placeholder 'woodcut' with the words in it."""

    def __init__(self, size=512):
        from PIL import Image, ImageDraw
        self.Image, self.ImageDraw, self.size = Image, ImageDraw, size

    def paint(self, prompt):
        s = self.size
        rnd = random.Random(prompt)
        img = self.Image.new("L", (s, s), 255)
        d = self.ImageDraw.Draw(img)
        horizon = rnd.randint(s // 3, 2 * s // 3)
        d.rectangle((0, 0, s, horizon), fill=0)                       # night sky
        for i in range(0, s, 9):                                     # carved lines
            d.line((0, horizon + i, s, horizon + i + rnd.randint(-20, 20)), fill=0, width=3)
        r = rnd.randint(30, 70)
        x = rnd.randint(r, s - r)
        d.ellipse((x - r, 40, x + r, 40 + 2 * r), fill=255)          # moon
        for _ in range(4):                                           # buildings
            w, h = rnd.randint(40, 110), rnd.randint(60, 220)
            x0 = rnd.randint(0, s - w)
            d.rectangle((x0, horizon - h, x0 + w, horizon), fill=0, outline=255, width=2)
        words = prompt.split('"')[1] if '"' in prompt else prompt
        d.rectangle((0, s - 60, s, s), fill=0)
        d.text((14, s - 44), words[:60].upper(), fill=255)
        return img.convert("RGB")


# ------------------------------------------------------------------ server
class Dreamer:
    def __init__(self, ears, painter, builder, gallery=None):
        self.ears, self.painter, self.builder = ears, painter, builder
        self.gallery = gallery
        self.gpu = threading.Lock()             # one model at a time on the GPU
        self.heard = self.painted = 0
        if gallery:
            os.makedirs(gallery, exist_ok=True)

    def hear(self, wav_bytes):
        audio = read_wav(wav_bytes)
        with self.gpu:
            t0 = time.time()
            text = clean_lyrics(self.ears.hear(audio))
            ms = int((time.time() - t0) * 1000)
        self.heard += 1
        if text:
            print(f"[hear] {text!r} ({ms} ms)", flush=True)
        return text, ms

    def paint(self, line):
        prompt = self.builder.build(line)
        with self.gpu:
            t0 = time.time()
            img = self.painter.paint(prompt)
            dt = time.time() - t0
        buf = io.BytesIO()
        img.save(buf, "PNG")
        png = buf.getvalue()
        self.painted += 1
        print(f"[paint #{self.painted}] {line!r} in {dt:.1f}s", flush=True)
        if self.gallery:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            with open(os.path.join(self.gallery, f"{stamp}.png"), "wb") as f:
                f.write(png)
            with open(os.path.join(self.gallery, f"{stamp}.txt"), "w") as f:
                f.write(f"line: {line}\nprompt: {prompt}\n")
        return png, prompt


def make_handler(dreamer, info):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quieter console
            pass

        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self, limit):
            n = int(self.headers.get("Content-Length", "0"))
            if not 0 < n < limit:
                raise ValueError("missing or too large request body")
            return self.rfile.read(n)

        def do_GET(self):
            if self.path.startswith("/health"):
                self._json(200, dict(ok=True, heard=dreamer.heard, painted=dreamer.painted, **info))
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            path = urllib.parse.urlparse(self.path).path
            try:
                if path == "/hear":
                    text, ms = dreamer.hear(self._body(10_000_000))
                    return self._json(200, {"text": text, "ms": ms})
                if path == "/paint":
                    line = json.loads(self._body(100_000)).get("line", "")
                    png, prompt = dreamer.paint(line)
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(png)))
                    self.send_header("X-Prompt", urllib.parse.quote(prompt))
                    self.end_headers()
                    self.wfile.write(png)
                    return
                return self._json(404, {"error": "not found"})
            except Exception as e:
                print(f"[error] {e}", flush=True)
                return self._json(500, {"error": str(e)})

    return Handler


def main():
    ap = argparse.ArgumentParser(description="Boombox Dream Server (Jetson)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--mock", action="store_true", help="no AI models, for testing")
    ap.add_argument("--whisper", default="small", help="tiny, base, small, medium")
    ap.add_argument("--language", default=None, help="e.g. en or de (default: detect)")
    ap.add_argument("--translate", action="store_true",
                    help="captions and images in English, whatever language is sung")
    ap.add_argument("--model", default="stabilityai/sd-turbo")
    ap.add_argument("--steps", type=int, default=1)
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--style", default=DEFAULT_STYLE, help="look of the images")
    ap.add_argument("--save-gallery", action="store_true", help="keep every image in ./gallery")
    a = ap.parse_args()

    if a.mock:
        ears, painter = MockEars(), MockPainter(a.size)
    else:
        ears = Ears(a.whisper, a.language, translate=a.translate)
        painter = Painter(a.model, a.steps, a.size)

    gallery = os.path.join(HERE, "gallery") if a.save_gallery else None
    dreamer = Dreamer(ears, painter, PromptBuilder(a.style), gallery)
    info = {"mode": "mock" if a.mock else "ai", "ears": ears.kind,
            "model": "mock" if a.mock else a.model}
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), make_handler(dreamer, info))
    print(f"Boombox Dream Server ready on port {a.port} ({info['mode']})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
