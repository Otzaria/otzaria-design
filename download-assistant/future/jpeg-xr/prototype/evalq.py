"""Size x quality of lossy codecs for the 24 book frames shipped at 250% only.

Pipeline modelled per frame: 250% source -> codec -> decoded straight RGBA -> VCL premultiply
-> Inno's TBitmapImage stretch (SPLINE16, research_a/inno_resample.py) to the target scale
(250% = same size, TBitmapImage just assigns) -> composite over the page colour #F6EDE5.
Compared with (a) the natively rendered frame at that scale and (b) the lossless 250% PNG run
through the same stretch (= what the 250%-only build shows), so (b) isolates the codec's own error.

Usage: python evalq.py <spec> [<spec> ...]     one JSON line per spec
  png                     lossless baseline (the 250% PNGs)
  jxr:<dir>               decoded .bgra + sizes.json from jxr250.ps1
  webp:<q>[:<aq>]         Pillow lossy WebP, alpha_quality aq (default 100), method 6
  cwebp:<args with ~>     cwebp.exe, e.g. cwebp:-q~90~-sharp_yuv~-m~6
  jpga:<q>[:<sub>]        premultiplied RGB as JPEG (sub 0=4:4:4, 2=4:2:0) + alpha as PNG
"""
import io
import json
import os
import subprocess
import sys
import tempfile
from multiprocessing import Pool

import numpy as np
from PIL import Image

from inno_resample import stretch, premultiply

HERE = os.path.dirname(os.path.abspath(__file__))
NATIVE = os.path.join(HERE, 'native')
CACHE = os.path.join(HERE, 'cache')
SCALES = (100, 150, 200, 250)
PAGE = np.array([0xF6, 0xED, 0xE5], np.float64)
CWEBP = os.path.join(HERE, '..', 'research_c', 'webp_out64', 'release-static', 'x64', 'bin', 'cwebp.exe')


def size_of(s):
    return int(220 * s / 100 + 0.5)


def native(s, i):
    return np.asarray(Image.open(os.path.join(NATIVE, f'book_{i:02d}_{s}.png')).convert('RGBA'))


def comp_straight(rgba):
    a = rgba[..., 3:4].astype(np.float64) / 255
    return np.round(rgba[..., :3] * a + PAGE * (1 - a))


def comp_premul(pm):
    a = pm[..., 3:4].astype(np.float64)
    return np.round(pm[..., :3].astype(np.float64) + PAGE * (255 - a) / 255)


def shown(pm250, s):
    n = size_of(s)
    out = pm250 if n == pm250.shape[0] else stretch(pm250, n, n)
    return comp_premul(out)


def refs(i):
    """(native composites, lossless-250 shown composites) per scale, cached."""
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f'ref_{i:02d}.npz')
    if os.path.exists(p):
        z = np.load(p)
        return {s: z[f'n{s}'] for s in SCALES}, {s: z[f'b{s}'] for s in SCALES}
    pm = premultiply(native(250, i))
    nat = {s: comp_straight(native(s, i)) for s in SCALES}
    base = {s: shown(pm, s) for s in SCALES}
    np.savez(p, **{f'n{s}': nat[s] for s in SCALES}, **{f'b{s}': base[s] for s in SCALES})
    return nat, base


# ---- codecs: return (bytes, premultiplied RGBA uint8 at 250%) ----

def c_png(i, arg):
    p = os.path.join(NATIVE, f'book_{i:02d}_250.png')
    return os.path.getsize(p), premultiply(native(250, i))


def c_jxr(i, d):
    d = os.path.join(HERE, d)
    sizes = json.load(open(os.path.join(d, 'sizes.json')))
    stem = f'book_{i:02d}_250'
    bgra = np.fromfile(os.path.join(d, stem + '.bgra'), np.uint8).reshape(550, 550, 4)
    return sizes[stem], premultiply(bgra[..., [2, 1, 0, 3]])


def c_webp(i, arg):
    parts = arg.split(':')
    q = int(parts[0])
    aq = int(parts[1]) if len(parts) > 1 else 100
    buf = io.BytesIO()
    Image.fromarray(native(250, i), 'RGBA').save(buf, 'WEBP', quality=q, alpha_quality=aq, method=6)
    dec = np.asarray(Image.open(io.BytesIO(buf.getvalue())).convert('RGBA'))
    return len(buf.getvalue()), premultiply(dec)


def c_cwebp(i, arg):
    args = arg.replace('~', ' ').split()
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, 'o.webp')
        subprocess.run([CWEBP, '-quiet'] + args + [os.path.join(NATIVE, f'book_{i:02d}_250.png'), '-o', out],
                       check=True)
        data = open(out, 'rb').read()
    dec = np.asarray(Image.open(io.BytesIO(data)).convert('RGBA'))
    return len(data), premultiply(dec)


def c_jpga(i, arg):
    parts = arg.split(':')
    q = int(parts[0])
    sub = int(parts[1]) if len(parts) > 1 else 0
    o = native(250, i)
    pm = premultiply(o)
    jb = io.BytesIO()
    Image.fromarray(pm[..., :3], 'RGB').save(jb, 'JPEG', quality=q, subsampling=sub, optimize=True)
    ab = io.BytesIO()
    Image.fromarray(o[..., 3], 'L').save(ab, 'PNG', optimize=True)
    rgb = np.asarray(Image.open(io.BytesIO(jb.getvalue())).convert('RGB'))
    a = o[..., 3:4]
    dec = np.concatenate([np.minimum(rgb, a), a], -1).astype(np.uint8)
    return len(jb.getvalue()) + len(ab.getvalue()), dec


CODECS = {'png': c_png, 'jxr': c_jxr, 'webp': c_webp, 'cwebp': c_cwebp, 'jpga': c_jpga}


def job(a):
    spec, i = a
    kind, _, arg = spec.partition(':')
    n, pm = CODECS[kind](i, arg)
    pm = np.ascontiguousarray(pm)  # the resampler port is ~200x slower on strided arrays
    nat, base = refs(i)
    r = {'bytes': n, 'frame': i}
    for s in SCALES:
        img = shown(pm, s)
        dn = np.abs(img - nat[s])
        db = np.abs(img - base[s])
        r[s] = (float((dn ** 2).mean()), float(dn.max()), float(np.percentile(dn, 99.9)),
                float((db ** 2).mean()), float(db.max()), int((db.max(-1) > 8).sum()))
    return r


def psnr(mse):
    return 99.0 if mse == 0 else round(10 * np.log10(255 ** 2 / mse), 2)


def run(spec, pool):
    rs = pool.map(job, [(spec, i) for i in range(24)])
    out = {'spec': spec, 'bytes': sum(r['bytes'] for r in rs)}
    for s in SCALES:
        v = np.array([r[s] for r in rs])
        out[s] = {'psnr_nat': psnr(v[:, 0].mean()), 'worst_nat': psnr(v[:, 0].max()),
                  'max_nat': int(v[:, 1].max()), 'p999_nat': v[:, 2].max(),
                  'psnr_codec': psnr(v[:, 3].mean()), 'worst_codec': psnr(v[:, 3].max()),
                  'max_codec': int(v[:, 4].max()), 'px_gt8_codec': int(v[:, 5].sum()),
                  'worst_frame': int(v[:, 0].argmax())}
    return out


if __name__ == '__main__':
    with Pool(3) as pool:
        for spec in sys.argv[1:]:
            print(json.dumps(run(spec, pool)), flush=True)
