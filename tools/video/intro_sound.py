"""랜딩페이지 소개 영상(intro.mp4)의 소리를 만든다.

녹음한 음원이나 남의 음악을 쓰지 않고 numpy 로 한 소리씩 합성한다. 저작권 걱정이 없고,
장면이 바뀌면 박자표(intro_cues.js)만 고쳐 다시 돌리면 소리도 같이 옮겨 간다.

    python3 tools/video/intro_sound.py 결과.wav

120 BPM. 앞부분(명단, 클릭 수)은 낮게 깔린 소리와 시계 소리로 긴장을 만들고, 수신픽 + 소통픽 = 신통픽
세 번에 맞춰 크게 치고, 앱이 움직이는 동안은 북과 베이스가 받쳐 준다. 화면의 클릭, 줄 나타남,
오류, 안내창에도 짧은 소리를 붙인다. 끝은 큰 화음 하나로 맺는다.
"""

import json
import os
import sys
import wave

import numpy as np

SR = 44100
HERE = os.path.dirname(os.path.abspath(__file__))
RNG = np.random.default_rng(7)


def load_cues():
    with open(os.path.join(HERE, 'intro_cues.js'), encoding='utf-8') as source:
        text = source.read()
    body = text[text.index('INTRO_CUES'):]
    return to_real_time(json.loads(body[body.index('{'):body.rindex('}') + 1]))


def to_real_time(cues):
    """박자표는 '끼워 넣기 전' 시각이다. insert.at 이후는 insert.dur 만큼 늦춰 실제 영상 시각으로 바꾼다."""
    ins = cues['insert']
    at, dur = ins['at'], ins['dur']

    def real(x):
        return x + dur if x >= at else x

    out = {}
    for key, value in cues.items():
        if key in ('bpm', 'insert'):
            out[key] = value
        elif key == 'total':
            out[key] = value + dur
        elif isinstance(value, list):
            out[key] = [real(x) for x in value]
        elif isinstance(value, dict):
            out[key] = {k: (real(v) if k in ('start', 'end') else v) for k, v in value.items()}
        else:
            out[key] = real(value)
    # 끼어든 장면 속 시각은 insert.at 부터 잰 값이라 at 만 더한다
    out['insert'] = {k: ([at + x for x in v] if isinstance(v, list) else at + v) for k, v in ins['cues'].items()}
    # 솟구치는 소리는 끼어든 장면이 끝난 뒤 첫 장면 바로 앞에서만 짧게 올린다
    r0, r1 = out['riser']
    out['riser'] = [max(r0, r1 - 1.6), r1]
    return out


def secs(n):
    return np.arange(int(n * SR)) / SR


def lowpass_fft(x, cutoff, order=2):
    """주파수 영역에서 깎는 저역 통과. 긴 소리에 쓴다 (파이썬 반복문 없이)."""
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / SR)
    spec *= 1 / (1 + (freqs / cutoff) ** (2 * order)) ** .5
    return np.fft.irfft(spec, len(x))


def highpass_fft(x, cutoff, order=2):
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / SR)
    ratio = (freqs / cutoff) ** (2 * order)
    spec *= (ratio / (1 + ratio)) ** .5
    return np.fft.irfft(spec, len(x))


def sweep_bandpass(noise, f0, f1, q=2.5):
    """가운데 주파수가 f0 에서 f1 로 옮겨 가는 띠 통과 (상태 변수 필터). 짧은 소리에만 쓴다."""
    out = np.zeros_like(noise)
    low = band = 0.0
    n = len(noise)
    freqs = np.geomspace(f0, f1, n)
    damp = 1 / q
    for i in range(n):
        f = 2 * np.sin(np.pi * min(freqs[i], SR / 6) / SR)
        high = noise[i] - low - damp * band
        band += f * high
        low += f * band
        out[i] = band
    return out


class Mix:
    def __init__(self, seconds):
        self.n = int(seconds * SR)
        self.dry = np.zeros((2, self.n))
        self.send = np.zeros((2, self.n))   # 울림(리버브)으로 보내는 몫

    def add(self, at, sig, gain=1.0, pan=0.0, verb=0.0):
        start = int(at * SR)
        if start >= self.n or len(sig) == 0:
            return
        sig = sig[:self.n - start] * gain
        left, right = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        for ch, g in ((0, left), (1, right)):
            self.dry[ch, start:start + len(sig)] += sig * g * 1.41
            if verb:
                self.send[ch, start:start + len(sig)] += sig * g * 1.41 * verb

    def render(self):
        ir_len = int(2.6 * SR)
        t = np.arange(ir_len) / SR
        out = self.dry.copy()
        for ch in range(2):
            ir = RNG.standard_normal(ir_len) * np.exp(-t * 2.6)
            ir = lowpass_fft(ir, 5200)
            ir[:int(.012 * SR)] = 0     # 앞쪽 잠깐 비우기 (먼저 마른 소리가 들리게)
            ir /= np.sqrt(np.sum(ir ** 2))
            size = 1 << int(np.ceil(np.log2(self.n + ir_len)))
            wet = np.fft.irfft(np.fft.rfft(self.send[ch], size) * np.fft.rfft(ir, size), size)[:self.n]
            out[ch] += wet * .55
        return out


# ── 악기 ─────────────────────────────────────────
def kick(strength=1.0):
    t = secs(.45)
    pitch = 46 + 120 * np.exp(-t * 28)
    phase = 2 * np.pi * np.cumsum(pitch) / SR
    body = np.sin(phase) * np.exp(-t * (7 / strength))
    click = RNG.standard_normal(len(t)) * np.exp(-t * 300) * .25
    return np.tanh((body + click) * 1.6) * .9


def boom(length=2.2):
    """크게 치는 소리의 바닥: 낮게 떨어지는 사인과 거친 숨소리."""
    t = secs(length)
    pitch = 38 + 90 * np.exp(-t * 9)
    sub = np.sin(2 * np.pi * np.cumsum(pitch) / SR) * np.exp(-t * 2.1)
    rumble = lowpass_fft(RNG.standard_normal(len(t)), 900) * np.exp(-t * 5) * .5
    crack = highpass_fft(RNG.standard_normal(len(t)), 2500) * np.exp(-t * 26) * .35
    return np.tanh((sub * 1.3 + rumble + crack) * 1.3)


def snare():
    t = secs(.3)
    noise = highpass_fft(RNG.standard_normal(len(t)), 1400) * np.exp(-t * 18)
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30) * .5
    return (noise * .7 + tone) * .8


def hat(open_=False):
    t = secs(.22 if open_ else .06)
    return highpass_fft(RNG.standard_normal(len(t)), 7500) * np.exp(-t * (16 if open_ else 70)) * .5


def saw(freq, t, detune=0.0):
    f = freq * (1 + detune)
    return 2 * ((t * f) % 1) - 1


def bass_note(freq, length):
    t = secs(length)
    tone = saw(freq, t) * .6 + np.sin(2 * np.pi * freq * t)
    env = np.minimum(1, t / .005) * np.exp(-t * 3.2)
    return lowpass_fft(tone, 420) * env


def pluck(freq, length=.18, bright=1.0):
    t = secs(length)
    tone = np.sin(2 * np.pi * freq * t) + .35 * np.sin(4 * np.pi * freq * t) * bright
    return tone * np.exp(-t * 26) * np.minimum(1, t / .002)


def mouse_click():
    t = secs(.05)
    a = highpass_fft(RNG.standard_normal(len(t)), 3000) * np.exp(-t * 400)
    b = np.zeros_like(a)
    gap = int(.028 * SR)
    b[gap:] = a[:len(a) - gap] * .6
    return (a + b) * .9


def bell(freq, length=1.4):
    t = secs(length)
    tone = (np.sin(2 * np.pi * freq * t) + .5 * np.sin(2 * np.pi * freq * 2.01 * t) * np.exp(-t * 4)
            + .25 * np.sin(2 * np.pi * freq * 3.02 * t) * np.exp(-t * 7))
    return tone * np.exp(-t * 3.5) * np.minimum(1, t / .003)


def error_buzz():
    t = secs(.32)
    f = np.where(t < .14, 392, 294)
    square = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR))
    return lowpass_fft(square, 2200) * np.exp(-((t % .16) * 9)) * .35


def keystroke():
    t = secs(.035)
    tick = highpass_fft(RNG.standard_normal(len(t)), 2600) * np.exp(-t * 260)
    thock = np.sin(2 * np.pi * 180 * t) * np.exp(-t * 160) * .4
    return tick * .7 + thock


def rewind(length):
    """테이프를 되감듯 높은 데서 낮게 미끄러지는 소리."""
    t = secs(length)
    f = 1800 * (0.12 ** (t / length))
    tone = np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)) * .3 + np.sin(2 * np.pi * np.cumsum(f * .5) / SR) * .5
    return lowpass_fft(tone, 3000) * np.sin(np.pi * t / length) ** .7


def pop():
    t = secs(.14)
    f = 420 + 900 * t / .14
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 22)


def whoosh(length=.6):
    noise = RNG.standard_normal(int(length * SR))
    swept = sweep_bandpass(noise, 300, 5200, q=1.6)
    t = secs(length)
    env = np.sin(np.pi * np.clip(t / length, 0, 1)) ** 2.2
    return swept * env * .9


def riser(length):
    noise = RNG.standard_normal(int(length * SR))
    swept = sweep_bandpass(noise, 250, 7000, q=3)
    t = secs(length)
    tone = np.sin(2 * np.pi * np.cumsum(180 * (6 ** (t / length))) / SR) * .25
    env = (t / length) ** 2.4
    return (swept + tone) * env


def pad_chord(freqs, length, cutoff=1400):
    t = secs(length)
    sig = np.zeros(len(t))
    for f in freqs:
        for d in (-.004, 0, .005):
            sig += saw(f, t, d) * .12
    env = np.minimum(1, t / .35) * np.minimum(1, (length - t) / .4)
    return lowpass_fft(sig, cutoff) * env


# ── 곡 ──────────────────────────────────────────
A1, F1, C2, G1 = 55.0, 43.65, 65.41, 49.0
CHORDS = [  # 한 마디(2초)씩: Am, F, C, G
    (A1, [220.0, 261.63, 329.63, 493.88]),
    (F1, [174.61, 220.0, 261.63, 392.0]),
    (C2, [196.0, 261.63, 329.63, 392.0]),
    (G1, [196.0, 246.94, 293.66, 440.0]),
]


def build(cues):
    total = cues['total']
    beat = 60 / cues['bpm']
    mix = Mix(total + .05)

    # 앞부분: 낮게 깔린 소리와 시계 소리
    p0, p1 = cues['pulse']
    t = secs(p1 - p0)
    drone = (np.sin(2 * np.pi * 55 * t) + .4 * saw(110, t, .003)) * np.minimum(1, t / 1.2)
    mix.add(p0, lowpass_fft(drone, 300) * np.minimum(1, (p1 - p0 - t) / .2), .32)
    k = 0
    at = p0 + .5
    while at < p1 - .2:
        mix.add(at, pluck(1760 if k % 4 == 0 else 1320, .05), .10 + .02 * (k % 4 == 0), pan=.25 if k % 2 else -.25)
        at += beat / 2
        k += 1
    for at in (p0 + .25, p0 + 2.0):
        mix.add(at, kick(.7), .45)

    # 서른 곳 점이 하나씩 켜질 때
    d = cues['dots']
    scale = [523.25, 587.33, 659.25, 783.99, 880.0]
    for i in range(d['count']):
        mix.add(d['start'] + i * d['step'], pluck(scale[i % 5] * (2 if i >= 15 else 1), .09), .16, pan=-.6 + 1.2 * (i % 6) / 5)

    # 클릭 수가 120 까지 올라갈 때
    c = cues['count']
    for i in range(c['ticks']):
        at = c['start'] + (c['end'] - c['start']) * (1 - (1 - i / c['ticks']) ** 1.6)
        mix.add(at, mouse_click(), .32, pan=RNG.uniform(-.5, .5))
        mix.add(at, pluck(700 + 1700 * i / c['ticks'], .04), .07)

    # 끼어드는 장면: 자판 소리, 체크, 꼬임, 처음으로 되돌아감
    ins = cues['insert']
    for key, words, pitch in (('typeA', 30, 1.0), ('typeB', 14, 1.25)):
        a0, a1 = ins[key]
        n_keys = int((a1 - a0) * 22)
        for i in range(n_keys):
            at = a0 + (a1 - a0) * i / n_keys + RNG.uniform(-.008, .008)
            mix.add(at, keystroke(), .30 + .08 * RNG.random(), pan=RNG.uniform(-.35, .35))
        for i in range(words):    # 한 사람(기관)을 다 칠 때마다 작은 소리
            mix.add(a0 + (a1 - a0) * (i + 1) / words, pluck(1046.5 * pitch, .05), .05)
        mix.add(a1, bell(1567.98 * pitch, .6), .12, verb=.4)
    for i, at in enumerate(ins['checks']):
        mix.add(at, pluck([783.99, 880.0, 987.77, 1046.5, 1174.66][i % 5], .1), .16, pan=.4)
    mix.add(ins['tangle'], error_buzz(), .4, pan=.4)
    mix.add(ins['rewind'] - .05, rewind(.55), .45, verb=.3)

    r0, r1 = cues['riser']
    mix.add(r0, riser(r1 - r0 - .06), .55, verb=.3)

    # 수신픽 + 소통픽 = 신통픽, 원칙 세 줄
    for i, at in enumerate(cues['slams']):
        big = i == 2
        mix.add(at, boom(2.6 if big else 1.6), .95 if big else .75, verb=.35)
        mix.add(at, kick(1.3), .7)
        root, notes = CHORDS[i % 4]
        stab = pad_chord([n * 2 for n in notes], .9 if not big else 2.0, cutoff=3200)
        mix.add(at, stab, .5 if big else .3, verb=.6)
        if big:
            mix.add(at, bell(880, 2.4) * .5 + bell(1318.5, 2.4) * .3, .35, verb=.8)
    for i, at in enumerate(cues['rules']):
        mix.add(at, boom(1.1), .55, verb=.3)
        mix.add(at, kick(1.0), .55)
        mix.add(at, bell([659.25, 783.99, 987.77][i], 1.0), .18, verb=.6)

    # 화음 바탕: 신통픽이 나온 뒤부터 끝까지
    pad = np.zeros(int(total * SR))
    bar = 2 * beat * 2
    start = cues['slams'][2]
    at = start
    k = 0
    while at < cues['finale']:
        root, notes = CHORDS[k % 4]
        length = min(bar, cues['finale'] - at)
        chunk = pad_chord(notes, length + .3, cutoff=1100 + 500 * (k % 2))
        s = int(at * SR)
        pad[s:s + len(chunk)] += chunk[:len(pad) - s]
        at += bar
        k += 1
    mix.add(0, pad, .38, verb=.5)

    # 북과 베이스: 앱이 움직이는 동안
    g0, g1 = cues['groove']
    offset = int(round((g0 - start) / bar))   # 화음 바탕과 같은 마디에서 같은 화음을 짚는다
    n_beats = int(round((g1 - g0) / beat))
    for b in range(n_beats):
        at = g0 + b * beat
        mix.add(at, kick(), .62)
        if b % 2 == 1:
            mix.add(at, snare(), .32, verb=.25)
        mix.add(at + beat / 2, hat(open_=b % 4 == 3), .22, pan=.3)
        mix.add(at, hat(), .10, pan=-.3)
        root, _ = CHORDS[(offset + b // 4) % 4]
        for half in (0, 1):
            note = root * (2 if half else 1)
            mix.add(at + half * beat / 2, bass_note(note, beat / 2 - .01), .42 if half else .5)

    # 화면 속 움직임
    for at in cues['whoosh']:
        mix.add(at - .35, whoosh(.6), .38, pan=RNG.uniform(-.4, .4), verb=.25)
    pent = [659.25, 739.99, 880.0, 987.77, 1108.73, 1318.5]
    for key in ('susinPaste', 'susinRows', 'sotongRows'):
        for i, at in enumerate(cues[key]):
            mix.add(at, pluck(pent[i % len(pent)] * (1.5 if key != 'susinPaste' else 1), .12), .14, pan=.4)
    for at in cues['clicks']:
        mix.add(at, mouse_click(), .7, pan=.2)
    for i, at in enumerate(cues['log']):
        if at in cues['error']:
            continue
        mix.add(at, bell(1046.5 + 130 * i, .5), .16, pan=.3, verb=.3)
    for at in cues['error']:
        mix.add(at, error_buzz(), .38, pan=.3)
    for at in cues['alert']:
        mix.add(at, bell(880, 1.2), .28, verb=.5)
        mix.add(at + .16, bell(1174.66, 1.4), .26, verb=.5)
    for at in cues['pops']:
        mix.add(at, pop(), .22, pan=.35)

    # 끝: 큰 화음 하나
    fin = cues['finale']
    mix.add(fin, boom(3.2), 1.0, verb=.4)
    mix.add(fin, kick(1.4), .75)
    final = pad_chord([220.0, 261.63, 329.63, 493.88, 659.25], total - fin, cutoff=2600)
    t = secs(len(final) / SR)
    mix.add(fin, final * np.exp(-t * .35), .6, verb=.7)
    mix.add(fin, bell(1318.5, 4.0) * .6 + bell(1975.5, 4.0) * .3, .28, verb=.9)
    mix.add(fin, lowpass_fft(saw(A1, t) * np.exp(-t * .6), 260), .45)
    # 만든 사람이 나올 때 작은 종소리 두 번
    mix.add(cues['credit'], bell(1318.5, 1.6), .12, pan=-.2, verb=.7)
    mix.add(cues['credit'] + .18, bell(1975.5, 1.6), .09, pan=.2, verb=.7)

    out = mix.render()[:, :int(total * SR)]
    # 마무리: 낮은 웅웅거림 빼고, 부드럽게 눌러 소리 크기를 맞추고, 끝을 닫는다
    out = np.stack([highpass_fft(ch, 30) for ch in out])
    out = np.tanh(out * 1.1) / np.tanh(1.1)
    out /= np.max(np.abs(out)) / .89
    fade = int(1.2 * SR)
    out[:, -fade:] *= np.linspace(1, 0, fade) ** 2
    out[:, :int(.01 * SR)] *= np.linspace(0, 1, int(.01 * SR))
    return out


def write_wav(path, stereo):
    data = (np.clip(stereo.T, -1, 1) * 32767).astype('<i2')
    with wave.open(path, 'wb') as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(SR)
        out.writeframes(data.tobytes())


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    write_wav(sys.argv[1], build(load_cues()))
    print(sys.argv[1])
    return 0


if __name__ == '__main__':
    sys.exit(main())
