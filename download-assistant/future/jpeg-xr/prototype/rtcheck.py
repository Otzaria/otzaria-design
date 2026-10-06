"""Checks the BMPs dumped by the runtime harness against the offline model of each path."""
import struct, sys, os
import numpy as np
from PIL import Image
from inno_resample import premultiply

RUN = sys.argv[1]

def bmp(p):
    b = open(p, 'rb').read()
    off = struct.unpack_from('<I', b, 10)[0]
    w, h = struct.unpack_from('<ii', b, 18)
    px = np.frombuffer(b, np.uint8, count=abs(w * h) * 4, offset=off).reshape(abs(h), w, 4)
    return px[..., [2, 1, 0, 3]]  # -> RGBA order (premultiplied)

def native(i):
    return np.asarray(Image.open(f'native/book_{i:02d}_250.png').convert('RGBA'))

def jxr(d, i):
    x = np.fromfile(f'jxr/{d}/book_{i:02d}_250.bgra', np.uint8).reshape(550, 550, 4)
    return x[..., [2, 1, 0, 3]]

def webp(i):
    return np.asarray(Image.open(f'rt/frames/W_book_{i:02d}.webp').convert('RGBA'))

models = {0: lambda i: premultiply(native(i)), 1: lambda i: premultiply(native(i)),
          2: lambda i: premultiply(jxr('ip_q14', i)), 3: lambda i: premultiply(jxr('i_q14', i)),
          4: lambda i: premultiply(webp(i))}
names = {0: 'PNG TPngImage', 1: 'PNG WIC', 2: 'JXR A (premul q14)', 3: 'JXR B (straight q14)', 4: 'WebP DLL'}
for p in range(5):
    mx = 0; flips = set(); viol = 0
    for i in range(24):
        got = bmp(os.path.join(RUN, f'p{p}_{i:02d}.bmp')).astype(int)
        exp = models[p](i).astype(int)
        d0 = np.abs(got - exp).max(); d1 = np.abs(got[::-1] - exp).max()
        flips.add('as-is' if d0 <= d1 else 'flipped')
        mx = max(mx, min(d0, d1))
        viol += int((got[..., :3] > got[..., 3:4]).sum())
    print(f'{names[p]:22s} max diff vs offline model {mx}  (rows {sorted(flips)}; rgb>alpha: {viol})')

a = bmp(os.path.join(RUN, 'A12_pbgra_request.bmp')).astype(int)
once = premultiply(jxr('ip_q14', 12)).astype(int)
twice = premultiply(np.concatenate([once[..., :3], once[..., 3:4]], -1).astype(np.uint8)).astype(int)
print('PBGRA request + AlphaFormat:=afPremultiplied -> max diff vs single premul', np.abs(a - once).max(),
      '; vs double premul', np.abs(a - twice).max())
s = bmp(os.path.join(RUN, 'A12_straight.bmp')).astype(int)
print('BGRA request (straight) -> max diff vs single premul', np.abs(s - once).max())
