"""Procedural animated illustrations for make_video.py (Pillow only, no external assets).

Each art_* function builds its cached layers once and returns an object with .frame(t, dur) -> RGB image.
Static layers are drawn at 2x and downsampled for smooth edges; moving parts are drawn on small 2x canvases.
All sizes are given in 1080p design units and scaled by k.
"""
import math
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ACCENT = (224, 138, 90)


def lerp(a, b, t):
    return a + (b - a) * t


def vgrad(w, h, stops):
    """Vertical gradient through [(pos 0..1, (r,g,b)), ...]."""
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        f = y / max(h - 1, 1)
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= f <= p1:
                u = (f - p0) / (p1 - p0 or 1)
                d.line([(0, y), (w, y)], fill=tuple(int(lerp(c0[i], c1[i], u)) for i in range(3)))
                break
    return img


_glow_cache = {}


def glow(diameter, color, strength=1.0, power=2.2):
    """Soft round light sprite (RGBA)."""
    key = (int(diameter), color, round(strength, 2), power)
    if key not in _glow_cache:
        base = Image.radial_gradient("L").resize((int(diameter), int(diameter)))
        alpha = base.point(lambda v: int((max(0.0, 1 - v / 175.0)) ** power * 255 * strength))  # radial_gradient hits ~181 at the sprite edge
        sprite = Image.new("RGBA", base.size, color + (0,))
        sprite.putalpha(alpha)
        _glow_cache[key] = sprite
    return _glow_cache[key]


def paste_center(frame, sprite, cx, cy, opacity=1.0):
    if opacity < 1.0:
        sprite = sprite.copy()
        sprite.putalpha(sprite.getchannel("A").point(lambda v: int(v * opacity)))
    frame.paste(sprite, (int(cx - sprite.width / 2), int(cy - sprite.height / 2)), sprite)


class Canvas:
    """Transparent 2x-supersampled drawing surface covering a w x h region."""

    def __init__(self, w, h, ss=2):
        self.w, self.h, self.ss = int(w), int(h), ss
        self.img = Image.new("RGBA", (self.w * ss, self.h * ss), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def _p(self, pts):
        return [(x * self.ss, y * self.ss) for x, y in pts]

    def poly(self, pts, fill):
        self.d.polygon(self._p(pts), fill=fill)

    def rect(self, x0, y0, x1, y1, fill):
        self.d.rectangle([x0 * self.ss, y0 * self.ss, x1 * self.ss, y1 * self.ss], fill=fill)

    def ellipse(self, x0, y0, x1, y1, fill):
        self.d.ellipse([x0 * self.ss, y0 * self.ss, x1 * self.ss, y1 * self.ss], fill=fill)

    def line(self, pts, fill, width=1):
        self.d.line(self._p(pts), fill=fill, width=max(1, int(width * self.ss)))

    def done(self):
        return self.img.reduce(self.ss)


def ridge_points(width, base, amp, seed, step=24):
    rnd = random.Random(seed)
    f = [(rnd.uniform(0.004, 0.012), rnd.uniform(0, 6.28), rnd.uniform(0.3, 1.0)) for _ in range(4)]
    pts = []
    for x in range(0, int(width) + step, step):
        y = base - amp * sum(a * (0.5 + 0.5 * math.sin(x * fr + ph)) for fr, ph, a in f) / sum(a for _, _, a in f)
        pts.append((x, y))
    return pts


def silhouette(width, height, base, amp, seed, color):
    c = Canvas(width, height)
    pts = ridge_points(width, base, amp, seed)
    c.poly(pts + [(width, height), (0, height)], color)
    return c.done()


def fog_layer(width, height, seed, color=(120, 110, 150)):
    rnd = random.Random(seed)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for _ in range(26):
        x, y = rnd.uniform(0, width), rnd.uniform(height * 0.2, height * 0.8)
        rw, rh = rnd.uniform(width * 0.05, width * 0.18), rnd.uniform(height * 0.06, height * 0.2)
        d.ellipse([x - rw, y - rh, x + rw, y + rh], fill=color + (rnd.randint(14, 34),))
    return img.filter(ImageFilter.GaussianBlur(height * 0.07))


class Particles:
    """Rising embers / drifting dust."""

    def __init__(self, n, W, H, k, color=ACCENT, speed=(10, 30), size=(1.5, 4), seed=3, rise=True):
        rnd = random.Random(seed)
        self.items = [(rnd.random(), rnd.random(), rnd.uniform(*speed), rnd.uniform(*size), rnd.uniform(0, 6.28)) for _ in range(n)]
        self.W, self.H, self.k, self.color, self.rise = W, H, k, color, rise

    def draw(self, draw, t, bright=0.8, bg=(20, 18, 24)):
        for x0, y0, sp, size, ph in self.items:
            dy = sp * self.k * t * (-3 if self.rise else 3)
            y = (y0 * self.H + dy) % (self.H + 20)
            x = x0 * self.W + math.sin(t * 0.7 + ph) * 28 * self.k
            b = bright * (0.45 + 0.55 * math.sin(t * 1.9 + ph) ** 2)
            col = tuple(int(bg[i] + (self.color[i] - bg[i]) * b) for i in range(3))
            r = size * self.k
            draw.ellipse([x - r, y - r, x + r, y + r], fill=col)


def twinkle_stars(n, W, H, seed, max_y=0.7):
    rnd = random.Random(seed)
    return [(rnd.random() * W, rnd.random() * H * max_y, rnd.uniform(0.8, 2.2), rnd.uniform(0, 6.28)) for _ in range(n)]


def draw_stars(draw, stars, t, k):
    for x, y, r, ph in stars:
        b = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * 1.6 + ph))
        c = int(150 + 105 * b)
        rr = r * k * (0.8 + 0.4 * b)
        draw.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(c, c, min(255, c + 15)))


def zoom(img, z, cx=0.5, cy=0.5):
    if z <= 1.001:
        return img
    W, H = img.size
    w, h = W / z, H / z
    x0, y0 = (W - w) * cx, (H - h) * cy
    return img.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h))


# ------------------------------------------------------------------ figures
def hooded_figure(c, x, y, s, step, cloak=(10, 9, 14), lean=0.0):
    """Cloaked silhouette standing at (x, y=feet). s = height in px; step -1..1 animates the walk."""
    sh = s
    # legs
    for sign in (-1, 1):
        lx = x + sign * 0.07 * sh + step * sign * 0.09 * sh
        c.line([(x, y - 0.38 * sh), (lx, y)], cloak, 0.06 * sh)
    # cloak body
    c.poly([(x - 0.13 * sh, y - 0.78 * sh), (x + 0.13 * sh, y - 0.78 * sh), (x + 0.2 * sh + lean * 0.05 * sh, y - 0.12 * sh), (x - 0.2 * sh, y - 0.12 * sh)], cloak)
    # hood
    c.ellipse(x - 0.1 * sh, y - 0.97 * sh, x + 0.1 * sh, y - 0.74 * sh, cloak)
    c.poly([(x - 0.1 * sh, y - 0.84 * sh), (x + 0.02 * sh, y - 1.0 * sh), (x + 0.1 * sh, y - 0.84 * sh)], cloak)
    return c


def fighter(c, x, y, s, facing, arm_angle, body=(12, 10, 16), blade=(205, 215, 230)):
    """Duelist silhouette. facing=+1 faces right. arm_angle in radians (0 = horizontal toward opponent, + = raised)."""
    sh = s
    c.line([(x, y - 0.42 * sh), (x - facing * 0.07 * sh, y)], body, 0.07 * sh)
    c.line([(x, y - 0.42 * sh), (x + facing * 0.12 * sh, y)], body, 0.07 * sh)
    c.poly([(x - 0.11 * sh, y - 0.76 * sh), (x + 0.11 * sh, y - 0.76 * sh), (x + 0.15 * sh, y - 0.36 * sh), (x - 0.15 * sh, y - 0.36 * sh)], body)
    c.ellipse(x - 0.075 * sh, y - 0.93 * sh, x + 0.075 * sh, y - 0.77 * sh, body)
    sx, sy = x + facing * 0.05 * sh, y - 0.68 * sh
    hx = sx + facing * math.cos(arm_angle) * 0.2 * sh
    hy = sy - math.sin(arm_angle) * 0.2 * sh
    c.line([(sx, sy), (hx, hy)], body, 0.055 * sh)
    tipx = hx + facing * math.cos(arm_angle + 0.15) * 0.52 * sh
    tipy = hy - math.sin(arm_angle + 0.15) * 0.52 * sh
    c.line([(hx, hy), (tipx, tipy)], blade, 0.022 * sh)
    return tipx, tipy


class Scene:
    def frame(self, t, dur):
        raise NotImplementedError


# ------------------------------------------------------------------ castle
class Castle(Scene):
    def __init__(self, W, H, k):
        self.W, self.H, self.k = W, H, k
        self.ext = int(W * 0.2)
        LW = W + self.ext
        self.sky = vgrad(W, H, [(0, (5, 7, 22)), (0.45, (26, 24, 66)), (0.75, (96, 62, 100)), (1, (170, 100, 100))])
        self.stars = twinkle_stars(110, W, H, 5, 0.55)
        self.moon = glow(int(H * 0.5), (190, 205, 255), 0.55, 2.6)
        self.far = silhouette(LW, H, H * 0.74, H * 0.2, 11, (38, 32, 74, 255))
        self.mid = silhouette(LW, H, H * 0.8, H * 0.12, 23, (24, 20, 48, 255))
        self.castle, self.windows = self._castle(LW)
        self.near = silhouette(LW, H, H * 0.96, H * 0.14, 41, (8, 7, 14, 255))
        self.fog = fog_layer(W * 2, int(H * 0.5), 9)
        self.fog2 = fog_layer(W * 2, int(H * 0.5), 19, (150, 120, 140))
        self.embers = Particles(55, W, H, k, seed=8)

    def _castle(self, LW):
        W, H = self.W, self.H
        c = Canvas(LW, H)
        ground = H * 0.82
        cx = LW * 0.5
        body, edge = (14, 12, 30, 255), (150, 205, 235, 170)
        wins = []
        c.rect(cx - 0.34 * W, ground - 0.1 * H, cx + 0.34 * W, ground + 0.2 * H, body)
        for i in range(34):  # crenellations
            x = cx - 0.34 * W + i * (0.68 * W / 34)
            c.rect(x, ground - 0.125 * H, x + 0.68 * W / 68, ground - 0.1 * H, body)
        towers = [(-0.31, 0.04, 0.2, 0.1), (-0.23, 0.05, 0.29, 0.14), (-0.13, 0.045, 0.37, 0.18), (0.0, 0.075, 0.56, 0.27),
                  (0.13, 0.045, 0.35, 0.17), (0.23, 0.05, 0.28, 0.13), (0.31, 0.04, 0.19, 0.09)]
        for dx, tw, th, rh in towers:
            x0, x1 = cx + dx * W - tw * W / 2, cx + dx * W + tw * W / 2
            top = ground - th * H
            c.rect(x0, top, x1, ground, body)
            apex = (cx + dx * W, top - rh * H)
            c.poly([(x0 - 0.004 * W, top), (x1 + 0.004 * W, top), apex], body)
            c.line([(x0 - 0.004 * W, top), apex], edge, 2)
            c.line([(x1 + 0.004 * W, top), apex], edge, 2)
            c.line([(x0, top), (x0, ground)], (150, 205, 235, 60), 2)
            for j in range(max(1, int(th * 9))):
                wx, wy = cx + dx * W, top + (0.04 + j * 0.055) * H
                if wy < ground - 0.06 * H:
                    wins.append((wx, wy))
        return c.done(), wins

    def frame(self, t, dur):
        W, H, k, ext = self.W, self.H, self.k, self.ext
        p = min(t / max(dur, 1), 1)
        fr = self.sky.copy()
        d = ImageDraw.Draw(fr)
        draw_stars(d, self.stars, t, k)
        paste_center(fr, self.moon, W * 0.8 - p * 30 * k, H * 0.2)
        d.ellipse([W * 0.8 - 36 * k - p * 30 * k, H * 0.2 - 36 * k, W * 0.8 + 36 * k - p * 30 * k, H * 0.2 + 36 * k], fill=(235, 240, 255))
        fr.paste(self.far, (int(-ext * 0.25 * p), 0), self.far)
        fr.paste(self.mid, (int(-ext * 0.45 * p), 0), self.mid)
        ox = int(-ext * 0.62 * p)
        fr.paste(self.castle, (ox, 0), self.castle)
        for i, (wx, wy) in enumerate(self.windows):
            b = 0.55 + 0.45 * math.sin(t * 2.3 + i * 1.7) ** 2
            if (i * 7) % 5 == 0 and math.sin(t * 0.8 + i) > 0.6:
                continue
            col = (int(255 * b), int(190 * b), int(110 * b))
            d.rectangle([wx + ox - 3 * k, wy, wx + ox + 3 * k, wy + 12 * k], fill=col)
        fx = int(-(t * 14 * k) % (W * 1.0))
        for fog, y, sp in ((self.fog2, H * 0.55, 10), (self.fog, H * 0.62, 18)):
            off = int(-(t * sp * k) % W)
            fr.paste(fog, (off - W, int(y)), fog)
            fr.paste(fog, (off, int(y)), fog)
        fr.paste(self.near, (int(-ext * 0.9 * p), 0), self.near)
        self.embers.draw(d, t, 0.9, (14, 12, 22))
        return zoom(fr, 1.0 + 0.07 * p, 0.5, 0.65)


# ------------------------------------------------------------------ salt mines
class Mines(Scene):
    def __init__(self, W, H, k):
        self.W, self.H, self.k = W, H, k
        self.bg = vgrad(W, H, [(0, (14, 12, 14)), (0.6, (36, 30, 30)), (1, (16, 14, 14))])
        rnd = random.Random(4)
        c = Canvas(W, H)
        for _ in range(60):  # rock mass blobs
            x, y, r = rnd.uniform(0, W), rnd.uniform(0, H * 0.8), rnd.uniform(40, 150) * k
            g = rnd.randint(20, 46)
            c.ellipse(x - r, y - r * 0.7, x + r, y + r * 0.7, (g + 6, g, g - 4, 120))
        self.rock = c.done().filter(ImageFilter.GaussianBlur(10 * k))
        c = Canvas(W, H)
        for i in range(26):  # stalactites
            x = rnd.uniform(0, W)
            wd, ln = rnd.uniform(18, 60) * k, rnd.uniform(0.08, 0.3) * H
            c.poly([(x - wd, 0), (x + wd, 0), (x + rnd.uniform(-8, 8) * k, ln)], (6, 5, 7, 255))
        c.rect(0, 0, W, 0.04 * H, (6, 5, 7, 255))
        c.poly([(0, H * 0.84), (W, H * 0.84), (W, H), (0, H)], (8, 7, 9, 255))
        self.fore = c.done()
        self.glow = glow(int(H * 1.1), (255, 170, 80), 0.75, 2.0)
        self.crystals = [(rnd.uniform(0, W), H * rnd.uniform(0.86, 0.97), rnd.uniform(1.5, 3.5), rnd.uniform(0, 6.28)) for _ in range(46)]
        self.dust = Particles(60, W, H, k, color=(255, 215, 150), speed=(4, 14), size=(1.2, 3), seed=12, rise=False)

    def frame(self, t, dur):
        W, H, k = self.W, self.H, self.k
        p = min(t / max(dur, 1), 1)
        fr = self.bg.copy()
        fr.paste(self.rock, (0, 0), self.rock)
        ang = 0.16 * math.sin(t * 1.4)
        px, py, ln = W * 0.76, H * 0.02, H * 0.34
        lx, ly = px + math.sin(ang) * ln, py + math.cos(ang) * ln
        flick = 0.85 + 0.15 * math.sin(t * 11) * math.sin(t * 3.1)
        paste_center(fr, self.glow, lx, ly, flick)
        fr.paste(self.fore, (0, 0), self.fore)
        d = ImageDraw.Draw(fr)
        d.line([(px, py), (lx, ly)], fill=(60, 50, 44), width=max(2, int(3 * k)))
        d.rectangle([lx - 9 * k, ly, lx + 9 * k, ly + 24 * k], fill=(255, 205, 120))
        d.rectangle([lx - 12 * k, ly - 5 * k, lx + 12 * k, ly], fill=(40, 34, 30))
        for x, y, r, ph in self.crystals:
            b = 0.25 + 0.75 * max(0, math.sin(t * 2.1 + ph)) ** 3
            col = tuple(int(30 + 225 * b) for _ in range(3))
            rr = r * k * (0.6 + 0.8 * b)
            d.polygon([(x, y - rr * 2), (x + rr, y), (x, y + rr), (x - rr, y)], fill=col)
        self.dust.draw(d, t, 0.8, (30, 26, 26))
        # hooded prisoner walking left -> right
        fx = lerp(W * 0.12, W * 0.62, p)
        step = math.sin(t * 5.0)
        size = H * 0.34
        c = Canvas(int(size * 0.8), int(size * 1.15))
        hooded_figure(c, c.w / 2, size * 1.05 + math.sin(t * 10) * 2 * k, size, step, lean=0.6)
        sprite = c.done()
        ground = H * 0.9
        d.ellipse([fx - size * 0.25, ground - 8 * k, fx + size * 0.25, ground + 10 * k], fill=(8, 7, 9))
        fr.paste(sprite, (int(fx - c.w / 2), int(ground - size * 1.05 - 0.0 * H + 0)), sprite)
        # chains-light vignette
        return zoom(fr, 1.0 + 0.05 * p, 0.5, 0.6)


# ------------------------------------------------------------------ arena duel
class Arena(Scene):
    def __init__(self, W, H, k):
        self.W, self.H, self.k = W, H, k
        self.sky = vgrad(W, H, [(0, (30, 22, 50)), (0.5, (140, 70, 80)), (0.7, (220, 140, 90)), (1, (60, 36, 40))])
        self.stars = twinkle_stars(40, W, H, 2, 0.3)
        c = Canvas(W, H)
        c.poly([(0, H * 0.62), (W, H * 0.62), (W, H), (0, H)], (22, 16, 24, 255))
        for i in range(0, int(W), int(46 * k)):  # crowd heads
            for row in range(3):
                x = i + (row % 2) * 23 * k
                y = H * (0.58 + 0.05 * row)
                c.ellipse(x - 13 * k, y - 13 * k, x + 13 * k, y + 13 * k, (10, 8, 14, 255))
                c.rect(x - 15 * k, y + 8 * k, x + 15 * k, y + 60 * k, (10, 8, 14, 255))
        self.stands = c.done()
        c = Canvas(W, H)
        c.poly([(0, H * 0.8), (W, H * 0.8), (W, H), (0, H)], (118, 82, 60, 255))
        c.ellipse(W * 0.2, H * 0.8, W * 0.8, H * 1.06, (136, 98, 72, 255))
        self.floor = c.done()
        self.banners = [(W * f, H * 0.05, (150, 40, 50) if i % 2 else (210, 160, 70)) for i, f in enumerate([0.1, 0.26, 0.42, 0.58, 0.74, 0.9])]
        self.glow = glow(int(H * 0.7), (255, 200, 140), 0.5, 2.4)
        self.embers = Particles(40, W, H, k, seed=21)

    def frame(self, t, dur):
        W, H, k = self.W, self.H, self.k
        p = min(t / max(dur, 1), 1)
        fr = self.sky.copy()
        d = ImageDraw.Draw(fr)
        draw_stars(d, self.stars, t, k)
        paste_center(fr, self.glow, W * 0.5, H * 0.55)
        for i, (bx, by, col) in enumerate(self.banners):
            d.line([(bx, by), (bx, by + H * 0.42)], fill=(20, 16, 20), width=max(2, int(5 * k)))
            wave = math.sin(t * 2.2 + i) * 14 * k
            d.polygon([(bx, by + 10 * k), (bx + 90 * k + wave, by + 40 * k), (bx + 70 * k + wave, by + 150 * k), (bx, by + 170 * k)], fill=col)
        fr.paste(self.stands, (0, int(math.sin(t * 6) * 1.5 * k)), self.stands)
        fr.paste(self.floor, (0, 0), self.floor)
        size = H * 0.4
        period = 1.5
        phase = (t % period) / period
        swing = math.sin(min(phase / 0.45, 1) * math.pi)  # 0 -> 1 -> 0 during the strike, then rest
        a_left = 0.15 + 0.9 * (1 - swing) * 0.0 + 0.85 * (1 - swing) * 0.5 + 0.2
        a_right = a_left
        ground = H * 0.9
        reg_h = int(size * 1.2)
        c = Canvas(W, reg_h)
        lx, rx = W * (0.4 + 0.012 * math.sin(t * 2)), W * (0.6 - 0.012 * math.sin(t * 2))
        ltip = fighter(c, lx, reg_h * 0.98, size, 1, 0.6 + 0.7 * swing)
        rtip = fighter(c, rx, reg_h * 0.98, size, -1, 0.6 + 0.7 * swing)
        sprite = c.done()
        fr.paste(sprite, (0, int(ground - reg_h * 0.98)), sprite)
        # sparks at the clash
        cx, cy = (ltip[0] + rtip[0]) / 2, ground - reg_h * 0.98 + (ltip[1] + rtip[1]) / 2
        since = (phase - 0.2) * period
        if 0 <= since < 0.5 and swing > 0:
            rnd = random.Random(int(t / period) * 13 + 5)
            for _ in range(18):
                ang, sp = rnd.uniform(-math.pi, 0), rnd.uniform(120, 420) * k
                x = cx + math.cos(ang) * sp * since
                y = cy + math.sin(ang) * sp * since + 600 * k * since * since
                f = 1 - since / 0.5
                r = 3.2 * k * f
                d.ellipse([x - r, y - r, x + r, y + r], fill=(255, int(190 + 60 * f), int(90 + 80 * f)))
            paste_center(fr, glow(int(180 * k), (255, 220, 160), 0.9, 2.0), cx, cy, max(0, 1 - since / 0.25))
        self.embers.draw(d, t, 0.9, (80, 50, 50))
        return zoom(fr, 1.0 + 0.05 * p, 0.5, 0.7)


# ------------------------------------------------------------------ balance scale
class BalanceScale(Scene):
    def __init__(self, W, H, k, pros, cons, start=1.0):
        self.W, self.H, self.k = W, H, k
        self.pros, self.cons = pros, cons
        self.bg = vgrad(W, H, [(0, (24, 20, 30)), (1, (10, 9, 12))])
        self.glow = glow(int(H * 1.2), (200, 150, 110), 0.28, 2.4)
        self.embers = Particles(35, W, H, k, seed=31)
        self.start = start
        from PIL import ImageFont
        self.font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Georgia.ttf", max(10, int(31 * k)))
        self.chips = [self._chip(txt, (214, 160, 96)) for txt in pros], [self._chip(txt, (200, 96, 96)) for txt in cons]

    def _chip(self, text, col):
        pad = int(14 * self.k)
        w = int(self.font.getlength(text)) + pad * 2
        h = int(self.font.size * 1.7)
        c = Canvas(w, h)
        c.d.rounded_rectangle([0, 0, w * 2 - 1, h * 2 - 1], radius=h, fill=(24, 20, 26, 240), outline=col + (255,), width=3)
        img = c.done()
        ImageDraw.Draw(img).text((pad, h * 0.17), text, font=self.font, fill=(238, 233, 224))
        return img

    def frame(self, t, dur):
        W, H, k = self.W, self.H, self.k
        fr = self.bg.copy()
        paste_center(fr, self.glow, W * 0.5, H * 0.45)
        d = ImageDraw.Draw(fr)
        n = max(len(self.pros), len(self.cons))
        span = max(dur - self.start - 1.2, 1.0)
        step = span / max(n, 1)
        landed = lambda i: self.start + i * step + 0.7
        wp = sum(ease_(t, self.start + i * step, 0.7) for i in range(len(self.pros)))
        wc = sum(ease_(t, self.start + i * step + step * 0.45, 0.7) for i in range(len(self.cons)))
        target = max(-0.16, min(0.16, (wc - wp) * 0.05))  # heavier side dips
        beam_ang = target + 0.012 * math.sin(t * 2.4) * (1 - min(1, t / 3))
        pivot = (W * 0.5, H * 0.3)
        arm = W * 0.27
        # pillar + base
        d.polygon([(pivot[0] - 14 * k, pivot[1]), (pivot[0] + 14 * k, pivot[1]), (pivot[0] + 22 * k, H * 0.9), (pivot[0] - 22 * k, H * 0.9)], fill=(70, 56, 46))
        d.polygon([(pivot[0] - 150 * k, H * 0.9), (pivot[0] + 150 * k, H * 0.9), (pivot[0] + 100 * k, H * 0.86), (pivot[0] - 100 * k, H * 0.86)], fill=(58, 46, 38))
        ends = []
        for sgn in (-1, 1):
            ex, ey = pivot[0] + sgn * arm * math.cos(beam_ang), pivot[1] + sgn * arm * math.sin(beam_ang)
            ends.append((ex, ey))
        d.line([ends[0], ends[1]], fill=(176, 138, 84), width=max(3, int(11 * k)))
        d.ellipse([pivot[0] - 20 * k, pivot[1] - 20 * k, pivot[0] + 20 * k, pivot[1] + 20 * k], fill=(214, 170, 100))
        pan_y = H * 0.33
        for si, (ex, ey) in enumerate(ends):
            py = ey + pan_y
            d.line([(ex, ey), (ex - 120 * k, py)], fill=(150, 120, 80), width=max(2, int(3 * k)))
            d.line([(ex, ey), (ex + 120 * k, py)], fill=(150, 120, 80), width=max(2, int(3 * k)))
            d.pieslice([ex - 140 * k, py - 38 * k, ex + 140 * k, py + 38 * k], 0, 180, fill=(190, 148, 90))
            d.ellipse([ex - 140 * k, py - 10 * k, ex + 140 * k, py + 10 * k], fill=(214, 172, 108))
            chips = self.chips[si]
            for i, chip in enumerate(chips):
                t0 = self.start + i * step + (step * 0.45 if si else 0)
                u = (t - t0) / 0.7
                if u <= 0:
                    continue
                e = min(1.0, u)
                e = 1 - (1 - e) ** 3
                stack_y = py - 10 * k - (i + 1) * (chip.height * 0.82)
                cy = lerp(-chip.height - 20 * k, stack_y, e)
                if si == 0:
                    paste_center(fr, glow(int(chip.width * 1.5), (214, 160, 96), 0.18), ex, cy + chip.height / 2, 1)
                fr.paste(chip, (int(ex - chip.width / 2), int(cy)), chip)
        self.embers.draw(d, t, 0.7, (20, 18, 24))
        return fr


def ease_(t, start, dur):
    u = max(0.0, min(1.0, (t - start) / dur))
    return 1 - (1 - u) ** 3


# ------------------------------------------------------------------ rating sky
class StarrySky(Scene):
    def __init__(self, W, H, k):
        self.W, self.H, self.k = W, H, k
        self.sky = vgrad(W, H, [(0, (4, 5, 18)), (0.6, (22, 20, 58)), (1, (60, 36, 70))])
        rnd = random.Random(6)
        neb = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        nd = ImageDraw.Draw(neb)
        for col in ((110, 70, 170), (60, 90, 170), (170, 80, 120)):
            for _ in range(5):
                x, y, r = rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(0.12, 0.3) * W
                nd.ellipse([x - r, y - r * 0.5, x + r, y + r * 0.5], fill=col + (22,))
        self.neb = neb.filter(ImageFilter.GaussianBlur(H * 0.08))
        self.stars = twinkle_stars(220, W, H, 1, 1.0)

    def frame(self, t, dur):
        W, H, k = self.W, self.H, self.k
        fr = self.sky.copy()
        fr.paste(self.neb, (int(-t * 5 * k % 40), 0), self.neb)
        d = ImageDraw.Draw(fr)
        draw_stars(d, self.stars, t, k)
        for i in range(3):  # shooting stars
            ph = (t * 0.22 + i * 0.37) % 1.0
            if ph < 0.12:
                u = ph / 0.12
                x0, y0 = W * (0.1 + 0.3 * i), H * (0.05 + 0.1 * i)
                x, y = x0 + u * 520 * k, y0 + u * 260 * k
                for j in range(14):
                    f = j / 14
                    c = int(255 * (1 - f) * (1 - u * 0.4))
                    d.ellipse([x - f * 120 * k - 2 * k, y - f * 60 * k - 2 * k, x - f * 120 * k + 2 * k, y - f * 60 * k + 2 * k], fill=(c, c, c))
        return fr


def burst(fr, cx, cy, since, k, color=ACCENT):
    """Sparkle burst for a star lighting up (since = seconds after ignition)."""
    if since < 0 or since > 0.9:
        return
    d = ImageDraw.Draw(fr)
    f = since / 0.9
    for i in range(12):
        ang = i * math.pi / 6
        r0, r1 = 40 * k + f * 90 * k, 40 * k + f * 90 * k + (1 - f) * 40 * k
        d.line([(cx + math.cos(ang) * r0, cy + math.sin(ang) * r0), (cx + math.cos(ang) * r1, cy + math.sin(ang) * r1)],
               fill=tuple(int(c * (1 - f) + 20 * f) for c in color), width=max(2, int(4 * k * (1 - f))))
    paste_center(fr, glow(int(300 * k), color, 0.6 * (1 - f), 2.0), cx, cy)


def build(name, W, H, k, **kw):
    return {"castle": Castle, "mines": Mines, "arena": Arena, "sky": StarrySky}[name](W, H, k) if name != "scale" else BalanceScale(W, H, k, kw["pros"], kw["cons"])
