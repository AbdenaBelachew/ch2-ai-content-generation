"""Offline procedural soundtrack: a stand-in for ACE-Step when no GPU is available.

Synthesizes an Ethiopian-flavoured acoustic bed in a Tizita-style pentatonic mode at the storyboard tempo:
  - drone (Masenqo-like sustained bowed pad)
  - plucked arpeggios (Krar-like, Karplus-Strong)
  - slow breathy melody with vibrato (Washint-like flute)
  - soft low hand-drum on the beat (Kebero-like)
Pure standard library, deterministic. It is a placeholder for the real ACE-Step output, not a replacement.
"""

import math
from pathlib import Path
import random
import struct
import wave

SR = 32000

# Tizita-style pentatonic on D: 1  2  b3  5  b6   (D E F A Bb)
_SCALE_HZ = [146.83, 164.81, 174.61, 220.00, 233.08, 293.66, 329.63, 349.23, 440.00, 466.16, 587.33]


def _mix_into(buf: list, start: float, samples: list, gain: float) -> None:
    i0 = int(start * SR)
    for i, v in enumerate(samples):
        j = i0 + i
        if j >= len(buf):
            break
        buf[j] += v * gain


def _pluck(freq: float, dur: float, rng: random.Random) -> list:
    n = int(dur * SR)
    period = max(2, int(SR / freq))
    ring = [rng.uniform(-1, 1) for _ in range(period)]
    out = []
    for i in range(n):
        k = i % period
        nxt = ring[(k + 1) % period]
        v = 0.5 * (ring[k] + nxt) * 0.996
        ring[k] = v
        out.append(v)
    # gentle fade to avoid clicks
    f = min(300, n)
    for i in range(f):
        out[n - 1 - i] *= i / f
    return out


def _flute(freq: float, dur: float) -> list:
    n = int(dur * SR)
    out = []
    atk, rel = 0.18, 0.35
    for i in range(n):
        t = i / SR
        env = min(1.0, t / atk) * min(1.0, (dur - t) / rel) if dur > rel else 1.0
        vib = 1.0 + 0.006 * math.sin(2 * math.pi * 5.2 * t) * min(1.0, t / 0.6)
        ph = 2 * math.pi * freq * vib * t
        breath = (random.random() - 0.5) * 0.04
        out.append(env * (math.sin(ph) + 0.25 * math.sin(2 * ph) + 0.08 * math.sin(3 * ph) + breath))
    return out


def _kebero(dur: float = 0.45, accent: float = 1.0) -> list:
    n = int(dur * SR)
    out = []
    phase = 0.0
    for i in range(n):
        t = i / SR
        f = 55 + 70 * math.exp(-t * 22)
        phase += 2 * math.pi * f / SR
        env = math.exp(-t * 9)
        out.append(accent * env * (math.sin(phase) + 0.08 * (random.random() - 0.5) * math.exp(-t * 60)))
    return out


def synthesize_ensemble(
    output_path: str | Path,
    duration: float = 80.0,
    tempo_bpm: float = 68.0,
    seed: int = 7,
) -> Path:
    rng = random.Random(seed)
    random.seed(seed)
    total = int(duration * SR)
    buf = [0.0] * total
    beat = 60.0 / tempo_bpm

    # Drone: D2 + A2 with a slow swell
    for freq, g in ((73.42, 0.10), (110.0, 0.06), (146.83, 0.03)):
        for i in range(total):
            t = i / SR
            swell = 0.75 + 0.25 * math.sin(2 * math.pi * t / 11.0)
            buf[i] += g * swell * (math.sin(2 * math.pi * freq * t) + 0.3 * math.sin(2 * math.pi * freq * 2.003 * t))

    # Krar-like arpeggio: eighth notes walking through the scale, enters at ~4s
    t = 4.0
    idx = 3
    while t < duration - 3:
        idx = max(0, min(len(_SCALE_HZ) - 1, idx + rng.choice([-2, -1, -1, 1, 1, 2])))
        accent = 1.0 if round((t - 4.0) / (beat / 2)) % 4 == 0 else 0.65
        _mix_into(buf, t, _pluck(_SCALE_HZ[idx], 1.6, rng), 0.12 * accent)
        t += beat / 2

    # Washint-like melody: long phrases from ~10s with rests
    t = 10.0
    idx = 5
    while t < duration - 6:
        idx = max(3, min(len(_SCALE_HZ) - 1, idx + rng.choice([-2, -1, 0, 1, 2])))
        ln = rng.choice([2, 3, 4]) * beat
        _mix_into(buf, t, _flute(_SCALE_HZ[idx], ln), 0.11)
        t += ln + rng.choice([0, 0, beat, 2 * beat])

    # Kebero: beats 1 and 3 of each bar (soft), enters at ~6s
    t = 6.0
    bar = 0
    while t < duration - 4:
        _mix_into(buf, t, _kebero(accent=1.0), 0.12)
        _mix_into(buf, t + 2 * beat, _kebero(accent=0.7), 0.09)
        _mix_into(buf, t + 3.5 * beat, _kebero(dur=0.25, accent=0.35), 0.06)
        t += 4 * beat
        bar += 1

    # Master: fades + peak normalize
    fi, fo = int(3.0 * SR), int(5.0 * SR)
    for i in range(min(fi, total)):
        buf[i] *= i / fi
    for i in range(min(fo, total)):
        buf[total - 1 - i] *= i / fo
    peak = max(1e-9, max(abs(v) for v in buf))
    scale = 0.85 / peak

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, v * scale)) * 32767)) for v in buf))
    return out_path


def _guitar_note(freq: float, dur: float, rng: random.Random, bright: float = 0.5) -> list:
    """Warm plucked nylon-string tone: Karplus-Strong with a smoothed excitation and gentle damping."""
    n = int(dur * SR)
    period = max(2, int(SR / freq))
    ring = [rng.uniform(-1, 1) for _ in range(period)]
    # Smooth the excitation (low-pass) so the pluck is soft, not hissy.
    for _ in range(3 if bright < 0.6 else 1):
        ring = [(ring[i] + ring[(i + 1) % period]) * 0.5 for i in range(period)]
    out = []
    for i in range(n):
        k = i % period
        v = 0.5 * (ring[k] + ring[(k + 1) % period]) * 0.9975
        ring[k] = v
        out.append(v)
    f = min(400, n)
    for i in range(f):
        out[n - 1 - i] *= i / f
    return out


def synthesize_guitar(
    output_path: str | Path,
    duration: float = 82.0,
    tempo_bpm: float = 68.0,
    seed: int = 11,
) -> Path:
    """Clean solo fingerpicked guitar in a Tizita-style D minor pentatonic mode, with a touch of room."""
    rng = random.Random(seed)
    total = int(duration * SR)
    buf = [0.0] * total
    beat = 60.0 / tempo_bpm
    step = beat / 2  # eighth notes

    # (bass, [arpeggio tones]) per bar: Dm, Dm, Bb, A
    bars = [
        (73.42, [146.83, 174.61, 220.00, 293.66, 349.23]),
        (73.42, [146.83, 174.61, 220.00, 293.66, 349.23]),
        (116.54, [174.61, 233.08, 293.66, 349.23]),
        (110.00, [220.00, 293.66, 349.23, 440.00]),
    ]
    pattern = [None, 1, 2, 3, 2, 3, 2, 1]  # None = bass note; ints index into the chord tones

    t = 1.0
    bar = 0
    while t < duration - 4:
        bass, tones = bars[bar % len(bars)]
        for pos, p_ in enumerate(pattern):
            when = t + pos * step
            if when >= duration - 3:
                break
            if p_ is None:
                _mix_into(buf, when, _guitar_note(bass, 2.4, rng, 0.4), 0.55)
            else:
                f = tones[min(p_, len(tones) - 1)]
                if bar % 8 == 7 and pos == 7:  # little melodic lift at the end of a phrase
                    f *= 2
                _mix_into(buf, when, _guitar_note(f, 1.8, rng), 0.34 if pos % 2 else 0.28)
        t += 8 * step
        bar += 1

    # Gentle room: two feedback combs
    for delay_s, fb in ((0.083, 0.30), (0.127, 0.22)):
        d = int(delay_s * SR)
        for i in range(d, total):
            buf[i] += buf[i - d] * fb

    fi, fo = int(2.5 * SR), int(5.0 * SR)
    for i in range(min(fi, total)):
        buf[i] *= i / fi
    for i in range(min(fo, total)):
        buf[total - 1 - i] *= i / fo
    peak = max(1e-9, max(abs(v) for v in buf))
    scale = 0.85 / peak

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, v * scale)) * 32767)) for v in buf))
    return out_path


def synthesize_soundtrack(
    output_path: str | Path,
    duration: float = 80.0,
    tempo_bpm: float = 68.0,
    style: str = "guitar",
) -> Path:
    """Offline soundtrack. style='guitar' (clean solo guitar, default) or 'ensemble' (drone+flute+drum)."""
    if style == "ensemble":
        return synthesize_ensemble(output_path, duration=duration, tempo_bpm=tempo_bpm)
    return synthesize_guitar(output_path, duration=duration, tempo_bpm=tempo_bpm)
