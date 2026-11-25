"""Mix music + UI sounds by <video>.events.json and mux them into the video.

Usage (from the repo root):
  .venv/bin/python promo/mix_audio.py <video.mp4> <out.mp4>
Audio (CC0): promo/audio — "Calm Ambient 1 (Synthwave 4k)" by The Cynic Project
(opengameart.org), Kenney Interface Sounds (kenney.nl).
"""
import json
import subprocess
import sys

import numpy as np

SR = 44100
AUDIO = 'promo/audio/'
MUSIC_GAIN, FADE_IN, FADE_OUT = 0.45, 1.0, 3.0
SFX = {  # kind: (file, gain)
    'msg': ('pluck_001.wav', 0.55),
    'warn': ('question_002.wav', 0.5),
    'done': ('confirmation_002.wav', 0.6),
}
BURST_GAIN = 0.6  # messages closer than 0.7 s apart are quieter, so the burst doesn't clatter


def decode(path, seconds=None):
    cmd = ['ffmpeg', '-v', 'error', '-i', path, '-ac', '2', '-ar', str(SR), '-f', 'f32le', '-']
    if seconds:
        cmd[3:3] = ['-t', str(seconds)]
    a = np.frombuffer(subprocess.run(cmd, check=True, capture_output=True).stdout, np.float32)
    return a.reshape(-1, 2).copy()


def main(video, out):
    meta = json.load(open(video + '.events.json'))
    n = int(meta['duration'] * SR)
    mix = np.zeros((n, 2), np.float32)

    music = decode(AUDIO + 'synthwave_4k.mp3', meta['duration'])[:n]
    env = np.ones(len(music), np.float32)
    fi, fo = int(FADE_IN * SR), int(FADE_OUT * SR)
    env[:fi] = np.linspace(0, 1, fi)
    env[-fo:] = np.linspace(1, 0, fo)
    mix[:len(music)] += music * env[:, None] * MUSIC_GAIN

    sounds = {k: decode(AUDIO + f) * g for k, (f, g) in SFX.items()}
    events = meta['events']
    for i, e in enumerate(events):
        s = sounds[e['kind']]
        near = any(abs(e['t'] - o['t']) < 0.7 for o in events if o is not e)
        gain = BURST_GAIN if e['kind'] == 'msg' and near else 1.0
        at = int(e['t'] * SR)
        part = s[:max(0, n - at)]
        mix[at:at + len(part)] += part * gain

    peak = np.abs(mix).max()
    if peak > 0.98:
        mix *= 0.98 / peak
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', video,
                    '-f', 'f32le', '-ar', str(SR), '-ac', '2', '-i', '-',
                    '-map', '0:v', '-map', '1:a', '-c:v', 'copy',
                    '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-ar', str(SR), '-c:a', 'aac', '-b:a', '192k',
                    '-shortest', '-movflags', '+faststart', out],
                   input=mix.astype(np.float32).tobytes(), check=True)
    print(out, f'peak {peak:.2f}')


if __name__ == '__main__':
    main(*sys.argv[1:3])
