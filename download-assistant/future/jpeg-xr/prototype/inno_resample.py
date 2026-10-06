"""numpy port of Inno Setup's Components/Resample.pas (StretchBmp, 32-bit premultiplied path).

This is what TBitmapImage does when Stretch=True and the bitmap is pf32bit with alpha:
a separable SPLINE16 filter (support 2, widened by the scale when shrinking), Q16.16 weights,
8-bit clamp after each pass, RGB clamped to <= A (premultiplied).
"""
import math

import numpy as np


def _weights(dst: int, src: int):
    scale = np.float32(src / dst)
    limit = np.float32(1.0) if scale < 1 else np.float32(1.0) / scale
    sup = np.float32(2.0) / limit
    rows = []
    for i in range(dst):
        center = np.float32((i + 0.5) * scale)
        taps, temps = [], []
        s = np.float32(0)
        for j in range(math.floor(center - sup), math.ceil(center + sup) + 1):
            x = np.float32(abs(np.float32(j) - center + np.float32(0.5)))
            if x > sup:
                continue
            x = np.float32(x * limit)
            if x < 1:
                y = np.float32(x * x * (x - np.float32(9 / 5)) - np.float32(1 / 5) * x + 1)
            else:
                y = np.float32((x - 1) ** 2 * (np.float32(-1 / 3) * (x - 1) + np.float32(4 / 5))
                               - np.float32(7 / 15) * (x - 1))
            if y == 0 or j < 0 or j >= src:
                continue
            taps.append(j)
            temps.append(y)
            s = np.float32(s + y)
        if s != 0:
            k = np.float32(65536) / s
            w = [int(np.round(np.float32(t * k))) for t in temps]
        else:
            taps, w = [], []
        rows.append((taps, w))
    return rows


def _pass(img: np.ndarray, dst: int, axis: int) -> np.ndarray:
    """img: int64 HxWx4 premultiplied BGRA; resample along axis (0 = vertical, 1 = horizontal)."""
    src = img.shape[axis]
    rows = _weights(dst, src)
    shape = list(img.shape)
    shape[axis] = dst
    out = np.empty(shape, np.int64)
    for i, (taps, w) in enumerate(rows):
        acc = np.full(img.take(0, axis=axis).shape, 32768, np.int64)
        for j, wt in zip(taps, w):
            acc += img.take(j, axis=axis) * wt
        a = acc[..., 3]
        ab = np.where(a > 0, np.where(a < (255 << 16), a >> 16, 255), 0)
        lim = ab << 16
        res = np.empty_like(acc)
        res[..., 3] = ab
        for c in range(3):
            v = acc[..., c]
            res[..., c] = np.where(v > 0, np.where(v < lim, v >> 16, ab), 0)
        if axis == 0:
            out[i] = res
        else:
            out[:, i] = res
    return out


def stretch(premul: np.ndarray, w: int, h: int) -> np.ndarray:
    """premul: uint8 HxWx4 (any channel order, alpha last). Returns uint8 h x w x 4."""
    src_h, src_w = premul.shape[:2]
    img = premul.astype(np.int64)
    if w * src_h < h * src_w:
        img = _pass(img, w, 1)
        img = _pass(img, h, 0)
    else:
        img = _pass(img, h, 0)
        img = _pass(img, w, 1)
    return img.astype(np.uint8)


def premultiply(straight: np.ndarray) -> np.ndarray:
    """VCL-style premultiply of straight RGBA uint8 (rounded)."""
    a = straight[..., 3:4].astype(np.int64)
    rgb = (straight[..., :3].astype(np.int64) * a + 127) // 255
    return np.concatenate([rgb, a], -1).astype(np.uint8)
