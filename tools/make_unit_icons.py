#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
皇帝之威 · 特色单位图标生成器

用途
    为 UNIT_NHS_RUISHI（锐士）与 UNIT_NHS_SCOUT（斥候）生成两套图标贴图：
      mod/icons/nhs_unitsNN.dds      纯字形，给地图旗帜与生产列表小图标用
      mod/icons/nhs_portraitNN.dds   带徽章底盘，给单位面板立绘用
    每张图横向 2 格：Index 0 = 锐士，Index 1 = 斥候（IconsPerRow=2、IconsPerColumn=1）。

为什么自己画
    游戏单位图集（Units256.dds 等）打包在资源包里，本机没有解包工具，取不到原始像素；
    从工坊 mod 挪图涉及他人版权。所以这里按 Civ6 的视觉语言重画：
    透明底、暖白到浅金渐变、深褐描边。

格式依据（不是猜的）
    创意工坊 1369684991（Resourceful / Amatheria）在 Icons/ 下自带 22/32/38/50/64/256 六档
    未压缩 DDS，游戏可正常加载。其头部特征：DDS + A8R8G8B8
    （pfFlags=0x41、bitCount=32、R=0xff0000 G=0xff00 B=0xff A=0xff000000）。
    本脚本沿用同一格式：每像素 4 字节，文件内字节序 B,G,R,A，带完整 mip 链。
    同一 mod 用 <ImportFiles> 把 dds 送进引擎——这一步漏了，图集注册成功也加载不到贴图。

尺寸档位
    单位图标六档见 Base/Assets/UI/Icons/Icons_Units.xml；
    立绘六档见 Icons_UnitPortraits.xml。

用法
    python tools/make_unit_icons.py             # 只出 DDS
    python tools/make_unit_icons.py --preview   # 同时出 PNG 到 tools/preview/
"""

import math
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.normpath(os.path.join(HERE, "..", "mod"))
ICON_DIR = os.path.join(MOD, "icons")
PREVIEW_DIR = os.path.join(HERE, "preview")

UNIT_SIZES = [256, 80, 50, 38, 32, 22]        # Icons_Units.xml
PORTRAIT_SIZES = [256, 200, 95, 70, 50, 38]   # Icons_UnitPortraits.xml

SS = 4                 # 超采样倍数
MIN_HALF_PX = 1.3      # 笔画在目标尺寸下的最小半宽（像素），防止小图线条消失

TOP_RGB = (255, 248, 226)     # 字形渐变：暖白
BOT_RGB = (210, 170, 90)      #          → 浅金
EDGE_RGB = (46, 31, 16)       # 描边：深褐
MED_TOP = (62, 47, 30)        # 徽章底盘渐变：深棕
MED_BOT = (30, 23, 15)
RING_RGB = (200, 160, 74)     # 徽章金环


# ---------------------------------------------------------------------------
# 基础图形（都只回答「这点是否在图形内」，栅格化时只扫自身包围盒）
# ---------------------------------------------------------------------------
class Disc(object):
    def __init__(self, cx, cy, r):
        self.cx, self.cy, self.r = cx, cy, r

    def bbox(self, w):
        return (int((self.cx - self.r) * w) - 1, int((self.cy - self.r) * w) - 1,
                int((self.cx + self.r) * w) + 2, int((self.cy + self.r) * w) + 2)

    def has(self, x, y):
        return (x - self.cx) ** 2 + (y - self.cy) ** 2 <= self.r ** 2


class Capsule(object):
    def __init__(self, x1, y1, x2, y2, r):
        self.x1, self.y1, self.x2, self.y2, self.r = x1, y1, x2, y2, r

    def bbox(self, w):
        r = self.r
        return (int((min(self.x1, self.x2) - r) * w) - 1, int((min(self.y1, self.y2) - r) * w) - 1,
                int((max(self.x1, self.x2) + r) * w) + 2, int((max(self.y1, self.y2) + r) * w) + 2)

    def has(self, x, y):
        dx, dy = self.x2 - self.x1, self.y2 - self.y1
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - self.x1) * dx + (y - self.y1) * dy) / L2))
        px, py = self.x1 + t * dx, self.y1 + t * dy
        return (x - px) ** 2 + (y - py) ** 2 <= self.r ** 2


class Poly(object):
    def __init__(self, pts):
        self.pts = pts

    def bbox(self, w):
        xs = [p[0] for p in self.pts]
        ys = [p[1] for p in self.pts]
        return (int(min(xs) * w) - 1, int(min(ys) * w) - 1,
                int(max(xs) * w) + 2, int(max(ys) * w) + 2)

    def has(self, x, y):
        inside = False
        pts = self.pts
        j = len(pts) - 1
        for i in range(len(pts)):
            xi, yi = pts[i]
            xj, yj = pts[j]
            if (yi > y) != (yj > y):
                if x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                    inside = not inside
            j = i
        return inside


def smooth_poly(points, iterations=1):
    """Chaikin 平滑（闭合折线）。次数别多——3 次会把马头磨成土豆。"""
    pts = list(points) + [points[0]]
    for _ in range(iterations):
        out = [pts[0]]
        for i in range(len(pts) - 1):
            p, q = pts[i], pts[i + 1]
            out.append((0.75 * p[0] + 0.25 * q[0], 0.75 * p[1] + 0.25 * q[1]))
            out.append((0.25 * p[0] + 0.75 * q[0], 0.25 * p[1] + 0.75 * q[1]))
        out.append(pts[-1])
        pts = out
    return pts


def _blade(x1, y1, x2, y2, t0, length, half_w):
    """沿线段方向在 t0 处生出一枚叶形矛头"""
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    px, py = -uy, ux
    bx, by = x1 + dx * t0, y1 + dy * t0
    tx, ty = bx + ux * length, by + uy * length
    mx, my = (bx + tx) / 2, (by + ty) / 2
    return [(bx + px * half_w * 0.55, by + py * half_w * 0.55),
            (mx + px * half_w, my + py * half_w),
            (tx, ty),
            (mx - px * half_w, my - py * half_w),
            (bx - px * half_w * 0.55, by - py * half_w * 0.55)]


def _w(design, size):
    """笔画半宽：大图用设计值，小图抬到最小可见宽度"""
    return max(design, MIN_HALF_PX / size)


# ---------------------------------------------------------------------------
# 两个字形（坐标 0..1，y 向下）
# ---------------------------------------------------------------------------
def shape_ruishi(size):
    """锐士：盾（正面）+ 斜置长矛。

    盾与矛是先秦步兵最基本的识别符号；「一块面 + 一根斜线」
    在 22px 下仍能读出轮廓，不会糊成一团。
    """
    sx1, sy1, sx2, sy2 = 0.27, 0.92, 0.72, 0.12
    fill = [Capsule(sx1, sy1, sx2, sy2, _w(0.025, size)),
            Poly(_blade(sx1, sy1, sx2, sy2, 0.86, 0.17, _w(0.040, size))),
            Disc(sx1, sy1, _w(0.032, size))]        # 杆尾铜镦

    shield = [(0.5 - 0.220, 0.29), (0.5 + 0.220, 0.29)]
    for i in range(1, 13):
        t = i / 12.0
        shield.append((0.5 + 0.220 * (1 - 0.78 * t ** 1.7),
                       0.29 + (0.82 - 0.29) * t ** 0.95))
    for i in range(12, -1, -1):
        t = i / 12.0
        shield.append((0.5 - 0.220 * (1 - 0.78 * t ** 1.7),
                       0.29 + (0.82 - 0.29) * t ** 0.95))
    fill.append(Poly(shield))

    cut = []
    if size >= 40:                                  # 盾心圆凸，小图不画（会退化成脏点）
        cut.append(Disc(0.5, 0.50, 0.058))
        cut.append(Disc(0.5, 0.50, 0.034))
    return fill, cut


def shape_chihou(size):
    """斥候：马首（左向，骑士棋式侧影）。

    斥候在中国兵制里是轻骑侦骑，马首最直接，也不与原版任何单位图标撞车。
    只做一次平滑：耳与鼻梁要留转折；鬃毛做成小锯齿而非大尖角。
    """
    raw = [
        (0.100, 0.600), (0.100, 0.515),            # 鼻端
        (0.170, 0.468), (0.260, 0.440),            # 鼻骨
        (0.340, 0.402), (0.380, 0.300),            # 额
        (0.400, 0.200), (0.442, 0.088),            # 耳前根 → 耳尖
        (0.492, 0.240), (0.552, 0.300),            # 耳后 → 项
        (0.612, 0.352), (0.636, 0.392), (0.604, 0.398),
        (0.672, 0.452), (0.694, 0.492), (0.662, 0.500),
        (0.734, 0.566), (0.754, 0.606), (0.722, 0.614),
        (0.792, 0.700), (0.808, 0.742), (0.776, 0.748),
        (0.816, 0.860),                            # 颈后底
        (0.560, 0.900), (0.470, 0.800),            # 颈底 → 喉
        (0.408, 0.706), (0.330, 0.658),            # 下颌 → 颊
        (0.220, 0.636), (0.140, 0.630),            # 下颌前
    ]
    fill = [Poly(smooth_poly(raw, iterations=1))]
    cut = []
    if size >= 40:
        cut.append(Disc(0.318, 0.500, 0.024))
        cut.append(Disc(0.318, 0.500, 0.012))
        cut.append(Disc(0.150, 0.566, 0.014))
    return fill, cut


ICONS = [("ruishi", shape_ruishi), ("chihou", shape_chihou)]


# ---------------------------------------------------------------------------
# 栅格化
# ---------------------------------------------------------------------------
def rasterize(fill, cut, w):
    cov = bytearray(w * w)
    for sh in fill:
        x0, y0, x1, y1 = sh.bbox(w)
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(w, x1), min(w, y1)
        for py in range(y0, y1):
            cy = (py + 0.5) / w
            row = py * w
            for px in range(x0, x1):
                if not cov[row + px] and sh.has((px + 0.5) / w, cy):
                    cov[row + px] = 1
    for sh in cut:
        x0, y0, x1, y1 = sh.bbox(w)
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(w, x1), min(w, y1)
        for py in range(y0, y1):
            cy = (py + 0.5) / w
            row = py * w
            for px in range(x0, x1):
                if cov[row + px] and sh.has((px + 0.5) / w, cy):
                    cov[row + px] = 0
    return cov


def _edges(cov, w):
    e = bytearray(w * w)
    for py in range(1, w - 1):
        row = py * w
        for px in range(1, w - 1):
            i = row + px
            if cov[i] and not (cov[i - 1] and cov[i + 1] and cov[i - w] and cov[i + w]):
                e[i] = 1
    return e


def render_glyph(size, build, ss=SS):
    """字形层：暖白→浅金渐变 + 深褐描边，透明底"""
    w = size * ss
    fill, cut = build(size)
    cov = rasterize(fill, cut, w)
    edge = _edges(cov, w)

    out = bytearray(size * size * 4)
    n = ss * ss
    for oy in range(size):
        t = oy / float(max(1, size - 1))
        base_r = TOP_RGB[0] + (BOT_RGB[0] - TOP_RGB[0]) * t
        base_g = TOP_RGB[1] + (BOT_RGB[1] - TOP_RGB[1]) * t
        base_b = TOP_RGB[2] + (BOT_RGB[2] - TOP_RGB[2]) * t
        for ox in range(size):
            a = 0
            e = 0
            for sy in range(ss):
                row = (oy * ss + sy) * w + ox * ss
                for sx in range(ss):
                    a += cov[row + sx]
                    e += edge[row + sx]
            if a == 0:
                continue
            k = min(1.0, (e / float(a)) * 1.15)
            r = int(base_r + (EDGE_RGB[0] - base_r) * k)
            g = int(base_g + (EDGE_RGB[1] - base_g) * k)
            b = int(base_b + (EDGE_RGB[2] - base_b) * k)
            o = (oy * size + ox) * 4
            out[o], out[o + 1], out[o + 2] = r, g, b
            out[o + 3] = a * 255 // n
    return bytes(out)


def render_medallion(size, ss=SS):
    """立绘层的底盘：深棕圆牌 + 金环，四周透明"""
    w = size * ss
    out = bytearray(size * size * 4)
    n = ss * ss
    R_IN, R_RING = 0.452, 0.492
    for oy in range(size):
        t = oy / float(max(1, size - 1))
        mr = MED_TOP[0] + (MED_BOT[0] - MED_TOP[0]) * t
        mg = MED_TOP[1] + (MED_BOT[1] - MED_TOP[1]) * t
        mb = MED_TOP[2] + (MED_BOT[2] - MED_TOP[2]) * t
        for ox in range(size):
            inner = ring = 0
            for sy in range(ss):
                cy = ((oy * ss + sy) + 0.5) / w - 0.5
                for sx in range(ss):
                    cx = ((ox * ss + sx) + 0.5) / w - 0.5
                    d2 = cx * cx + cy * cy
                    if d2 <= R_IN * R_IN:
                        inner += 1
                    elif d2 <= R_RING * R_RING:
                        ring += 1
            if inner == 0 and ring == 0:
                continue
            ia = inner * 236 // n
            ra = ring * 255 // n
            o = (oy * size + ox) * 4
            if ra > ia:                     # 环压在底盘外沿
                out[o], out[o + 1], out[o + 2] = RING_RGB
                out[o + 3] = ra
            else:
                out[o], out[o + 1], out[o + 2] = int(mr), int(mg), int(mb)
                out[o + 3] = ia
    return bytes(out)


def _over(fg, bg, size):
    """fg 叠在 bg 上（直通 alpha）"""
    out = bytearray(size * size * 4)
    for i in range(0, size * size * 4, 4):
        fa = fg[i + 3]
        ba = bg[i + 3]
        if fa == 0:
            out[i:i + 4] = bg[i:i + 4]
            continue
        if ba == 0:
            out[i:i + 4] = fg[i:i + 4]
            continue
        oa = fa + ba * (255 - fa) // 255
        for k in range(3):
            out[i + k] = (fg[i + k] * fa + bg[i + k] * ba * (255 - fa) // 255) // max(1, oa)
        out[i + 3] = oa
    return bytes(out)


def render_tile(size, build, medallion=False):
    glyph = render_glyph(size, build)
    if not medallion:
        return glyph
    # 立绘档位：字形略缩，给金环留出边距
    inner = int(size * 0.74)
    if inner < 8:
        return glyph
    small = render_glyph(inner, build)
    canvas = bytearray(size * size * 4)
    off = (size - inner) // 2
    for y in range(inner):
        dst = ((y + off) * size + off) * 4
        canvas[dst:dst + inner * 4] = small[y * inner * 4:(y + 1) * inner * 4]
    return _over(bytes(canvas), render_medallion(size), size)


def build_atlas(size, medallion):
    w = size * 2
    buf = bytearray(w * size * 4)
    for idx, (_, build) in enumerate(ICONS):
        tile = render_tile(size, build, medallion)
        for y in range(size):
            src = y * size * 4
            dst = (y * w + idx * size) * 4
            buf[dst:dst + size * 4] = tile[src:src + size * 4]
    return bytes(buf)


# ---------------------------------------------------------------------------
# DDS / PNG 输出
# ---------------------------------------------------------------------------
def _downsample(rgba, w, h):
    """2×2 盒式降采样，先预乘再平均，避免透明像素把边缘拖黑"""
    nw, nh = max(1, w // 2), max(1, h // 2)
    out = bytearray(nw * nh * 4)
    for y in range(nh):
        for x in range(nw):
            ar = ag = ab = aa = 0
            for dy in range(2):
                sy = min(h - 1, y * 2 + dy)
                for dx in range(2):
                    i = (sy * w + min(w - 1, x * 2 + dx)) * 4
                    a = rgba[i + 3]
                    ar += rgba[i] * a
                    ag += rgba[i + 1] * a
                    ab += rgba[i + 2] * a
                    aa += a
            if aa == 0:
                continue
            o = (y * nw + x) * 4
            out[o] = min(255, ar // aa)
            out[o + 1] = min(255, ag // aa)
            out[o + 2] = min(255, ab // aa)
            out[o + 3] = aa // 4
    return bytes(out), nw, nh


def write_dds(path, rgba, w, h):
    mips = [(rgba, w, h)]
    cur, cw, ch = rgba, w, h
    while cw > 1 or ch > 1:
        cur, cw, ch = _downsample(cur, cw, ch)
        mips.append((cur, cw, ch))

    flags = 0x100F | 0x20000
    caps = 0x1000 | 0x8 | 0x400000
    hdr = bytearray(b"DDS ")
    hdr += struct.pack("<I", 124)
    hdr += struct.pack("<I", flags)
    hdr += struct.pack("<I", h)
    hdr += struct.pack("<I", w)
    hdr += struct.pack("<I", w * 4)
    hdr += struct.pack("<I", 0)
    hdr += struct.pack("<I", len(mips))
    hdr += b"\x00" * 44
    hdr += struct.pack("<I", 32)
    hdr += struct.pack("<I", 0x41)
    hdr += struct.pack("<I", 0)
    hdr += struct.pack("<I", 32)
    hdr += struct.pack("<I", 0x00FF0000)
    hdr += struct.pack("<I", 0x0000FF00)
    hdr += struct.pack("<I", 0x000000FF)
    hdr += struct.pack("<I", 0xFF000000)
    hdr += struct.pack("<I", caps)
    hdr += struct.pack("<I", 0) * 4

    body = bytearray()
    for data, mw, mh in mips:
        for i in range(0, len(data), 4):          # 文件内 B,G,R,A
            body += bytes((data[i + 2], data[i + 1], data[i], data[i + 3]))
    with open(path, "wb") as fp:
        fp.write(bytes(hdr) + bytes(body))
    return len(hdr) + len(body)


def write_png(path, rgba, w, h):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgba[y * w * 4:(y + 1) * w * 4]

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + \
            struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as fp:
        fp.write(png)


def main():
    preview = "--preview" in sys.argv
    os.makedirs(ICON_DIR, exist_ok=True)
    if preview:
        os.makedirs(PREVIEW_DIR, exist_ok=True)

    jobs = [("nhs_units", UNIT_SIZES, False), ("nhs_portrait", PORTRAIT_SIZES, True)]
    total_files = total_bytes = 0
    for prefix, sizes, med in jobs:
        for size in sizes:
            rgba = build_atlas(size, med)
            path = os.path.join(ICON_DIR, "%s%d.dds" % (prefix, size))
            n = write_dds(path, rgba, size * 2, size)
            total_files += 1
            total_bytes += n
            print("  %-24s %4dx%-4d %7.1f KB" % (os.path.basename(path), size * 2, size, n / 1024.0))
            if preview:
                write_png(os.path.join(PREVIEW_DIR, "%s%d.png" % (prefix, size)),
                          rgba, size * 2, size)
    print("共 %d 个 DDS，%.1f KB" % (total_files, total_bytes / 1024.0))
    if preview:
        print("预览 PNG 已写入 tools/preview/")


if __name__ == "__main__":
    main()
