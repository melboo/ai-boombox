#!/usr/bin/env python3
"""
Boombox Visuals v2 - live beat detection

Listens to whatever the Pi is playing (Spotify, Bluetooth, files) by
recording the "monitor" of the sound output, and finds the beats in
real time. No song files or analysis in advance needed.
"""
import collections
import subprocess
import threading
import time

import numpy as np

RATE = 44100
HOP = 512                 # new samples per step: ~11.6 ms
NFFT = 1024               # analysis window: ~23 ms
MIN_BEAT_GAP = 0.28       # seconds; fastest beat we accept (~214 BPM)
SILENCE_RMS = 0.003       # below this counts as silence
IDLE_AFTER = 2.5          # seconds of silence before the idle screen


class BeatDetector:
    """Feed it audio in chunks of HOP samples; ask it for the current visual state."""

    def __init__(self, rate=RATE):
        self.rate = rate
        self.buf = np.zeros(NFFT, np.float32)
        self.win = np.hanning(NFFT).astype(np.float32)
        freqs = np.fft.rfftfreq(NFFT, 1.0 / rate)
        self.low_bins = (freqs >= 35) & (freqs <= 160)    # kick drum / bass
        self.prev_low = 0.0
        self.flux_hist = collections.deque(maxlen=int(rate / HOP * 1.5))
        self.last_beat = -1e9
        self.beats = collections.deque(maxlen=64)          # (time, count)
        self.count = 0
        self.bass_peak = 1e-6
        self.rms_peak = 1e-6
        self.bass = 0.0
        self.loud = 0.0
        self.last_sound = -1e9
        self.lock = threading.Lock()
        # The last ~15 s of raw audio, for sending to the Jetson (lyrics -> images)
        self.history = collections.deque(maxlen=int(rate / HOP * 15))

    def recent_audio(self, seconds):
        """The last `seconds` of what was playing, as float32 mono at self.rate."""
        n = int(seconds * self.rate / HOP)
        with self.lock:
            chunks = list(self.history)[-n:]
        return np.concatenate(chunks) if chunks else np.zeros(0, np.float32)

    def feed(self, chunk, t):
        """chunk: float32 mono samples (-1..1), length HOP. t: time the chunk arrived."""
        with self.lock:
            self.history.append(chunk)
        self.buf = np.concatenate((self.buf[len(chunk):], chunk))
        rms = float(np.sqrt(np.mean(chunk * chunk)))
        spec = np.abs(np.fft.rfft(self.buf * self.win))
        low = float(spec[self.low_bins].sum())

        # How much did the bass jump since the last step? (log so volume matters less)
        low_c = float(np.log1p(low))
        flux = max(0.0, low_c - self.prev_low)
        self.prev_low = low_c

        hist = self.flux_hist
        if len(hist) > 10:
            thr = float(np.mean(hist) + 1.5 * np.std(hist))
        else:
            thr = 1e9
        hist.append(flux)

        # Automatic gain: levels are relative to the recent loudest moment
        self.bass_peak = max(low, self.bass_peak * 0.9995)
        self.rms_peak = max(rms, self.rms_peak * 0.9995)
        silent = rms < SILENCE_RMS

        with self.lock:
            self.bass = 0.0 if silent else min(1.0, low / self.bass_peak)
            self.loud = 0.0 if silent else min(1.0, rms / self.rms_peak)
            if not silent:
                self.last_sound = t
            if (not silent) and flux > thr and flux > 0.15 and t - self.last_beat > MIN_BEAT_GAP:
                self.last_beat = t
                self.beats.append((t, self.count))
                self.count += 1

    def state(self, now, delay=0.0):
        """What the visuals should show at time `now`, shown `delay` seconds late."""
        t = now - delay
        with self.lock:
            past = [(bt, n) for bt, n in self.beats if bt <= t]
            active = now - self.last_sound < IDLE_AFTER
            bass, loud = self.bass, self.loud
        if past:
            bt, n = past[-1]
            since, strong = t - bt, n % 4 == 0      # every 4th beat = start of a bar
        else:
            n, since, strong = -1, 99.0, False
        ring_ages = [t - bt for bt, _ in past[-3:]][::-1]
        tempo = 0.0
        if len(past) >= 5:
            gaps = np.diff([bt for bt, _ in past[-12:]])
            gaps = gaps[gaps < 1.5]
            if len(gaps):
                tempo = 60.0 / float(np.median(gaps))
        return {
            "active": active,
            "beat_n": n,          # number of the last beat (changes on every beat)
            "since": since,
            "strong": strong,
            "bass": bass,
            "loud": loud,
            "ring_ages": ring_ages,
            "tempo": tempo,
        }


class Capture(threading.Thread):
    """Records what the Pi is playing and feeds it to the detector, forever."""

    CMD = [
        "parec", "--device=@DEFAULT_MONITOR@", "--raw", "--format=s16le",
        f"--rate={RATE}", "--channels=1", "--latency-msec=20",
    ]

    def __init__(self, detector):
        super().__init__(daemon=True)
        self.detector = detector
        self.error = None

    def run(self):
        nbytes = HOP * 2
        while True:
            try:
                proc = subprocess.Popen(self.CMD, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                self.error = "parec missing - run install.sh"
                return
            self.error = None
            while True:
                data = proc.stdout.read(nbytes)
                if len(data) < nbytes:
                    break
                chunk = np.frombuffer(data, "<i2").astype(np.float32) / 32768.0
                self.detector.feed(chunk, time.monotonic())
            proc.wait()
            self.error = "audio capture stopped, retrying"
            time.sleep(1)
