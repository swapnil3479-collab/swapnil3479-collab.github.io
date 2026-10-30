"""Render an animated, narrated review video (+ thumbnail + YouTube metadata) for a published post.

Usage:
  make_video.py <slug> [--script .tmp/<slug>_video.json] [--res 1080|720|360] [--voice en-GB-SoniaNeural]
                       [--max-seconds N]   (quick low-res preview: --res 360 --max-seconds 20)

Inputs:  content/posts/<slug>.md (title, author, cover, rating...) and a scene script JSON written by the agent
         (see workflows/make_review_video.md for the format).
Outputs: .tmp/videos/<slug>/<slug>.mp4, <slug>_thumbnail.png, <slug>_youtube.json (title, description with
         chapter timestamps, tags). Nothing is uploaded here.

Free/local stack: Pillow draws frames, edge-tts (Microsoft's free online voices; falls back to macOS `say`)
makes the narration, and the system ffmpeg (brew install ffmpeg) encodes the video.
"""
import argparse, asyncio, hashlib, json, math, random, re, subprocess, sys
from pathlib import Path

import requests
import yaml
import shutil
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_site import SITE  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"  # system ffmpeg (brew install ffmpeg); the pip-bundled one hung on macOS
if not Path(FFMPEG).exists():
    sys.exit("ffmpeg not found. Install it with: brew install ffmpeg")
FPS = 24
LEAD, TAIL = 0.5, 0.8  # seconds of silence before/after each scene's narration
BG_TOP, BG_BOT = (30, 27, 24), (14, 13, 12)
TEXT, MUTED, ACCENT, WARN = (238, 233, 224), (163, 157, 146), (224, 138, 90), (214, 110, 110)
FONT_DIR = Path("/System/Library/Fonts/Supplemental")


def font(name, size):
    try:
        return ImageFont.truetype(str(FONT_DIR / name), size)
    except OSError:
        return ImageFont.load_default(size)


# ---------------------------------------------------------------- helpers
def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ramp(t, start, dur):
    return ease((t - start) / dur) if dur > 0 else 1.0


def paste(frame, layer, xy, opacity=1.0):
    if opacity <= 0.01:
        return
    if opacity >= 0.99:
        frame.paste(layer, xy, layer)
    else:
        mask = layer.getchannel("A").point(lambda v: int(v * opacity))
        frame.paste(layer, xy, mask)


def wrap(text, fnt, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if fnt.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + ([cur] if cur else [])


def text_layer(text, fnt, color, max_w, spacing=1.3, align="left"):
    lines = wrap(text, fnt, max_w)
    lh = int(fnt.size * spacing)
    w = int(max((fnt.getlength(l) for l in lines), default=1)) + 4
    img = Image.new("RGBA", (max(w, 1), lh * max(len(lines), 1) + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        x = {"left": 0, "center": (w - fnt.getlength(line)) / 2}[align]
        d.text((x, i * lh), line, font=fnt, fill=color)
    return img


def star_points(cx, cy, r):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    return pts


# ---------------------------------------------------------------- TTS
def audio_duration(path):
    out = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])


def synth(text, voice, cache_dir):
    key = hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()[:16]
    mp3 = cache_dir / f"{key}.mp3"
    if mp3.exists():
        return mp3
    try:
        import edge_tts

        asyncio.run(edge_tts.Communicate(text, voice, rate="-4%").save(str(mp3)))
        if mp3.stat().st_size < 1000:
            raise RuntimeError("empty audio")
    except Exception as e:  # offline or service change: macOS voice as a fallback
        print(f"edge-tts failed ({e}); falling back to macOS 'say'", file=sys.stderr)
        aiff = cache_dir / f"{key}.aiff"
        subprocess.run(["say", "-v", "Daniel", "-o", str(aiff), text], check=True)
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(aiff), str(mp3)], check=True)
    return mp3


# ---------------------------------------------------------------- video
class Video:
    def __init__(self, res, post, script, cover, total):
        self.k = res / 1080
        self.W, self.H = int(1920 * self.k) // 2 * 2, int(1080 * self.k) // 2 * 2
        self.post, self.script, self.total = post, script, total
        self.cover = cover
        k = self.k
        self.f_tag = font("Georgia Bold.ttf", int(30 * k))
        self.f_title = font("Georgia Bold.ttf", int(100 * k))
        self.f_h1 = font("Georgia Bold.ttf", int(64 * k))
        self.f_body = font("Georgia.ttf", int(52 * k))
        self.f_sub = font("Georgia Italic.ttf", int(40 * k))
        self.f_cap = font("Georgia.ttf", int(38 * k))
        self.f_big = font("Georgia Bold.ttf", int(150 * k))
        self.bg = self._background()
        rnd = random.Random(7)
        self.embers = [(rnd.random(), rnd.random(), rnd.uniform(6, 22), rnd.uniform(2, 6), rnd.uniform(0, 6.28)) for _ in range(70)]

    def _background(self):
        W, H = self.W, self.H
        img = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(img)
        for y in range(H):
            f = y / H
            d.line([(0, y), (W, y)], fill=tuple(int(BG_TOP[i] * (1 - f) + BG_BOT[i] * f) for i in range(3)))
        return img

    def frame(self, t):
        fr = self.bg.copy()
        d = ImageDraw.Draw(fr)
        for x0, y0, sp, size, ph in self.embers:
            y = (y0 * self.H - sp * self.k * t * 3) % (self.H + 20)
            x = x0 * self.W + math.sin(t * 0.6 + ph) * 30 * self.k
            b = 0.25 + 0.25 * math.sin(t * 1.7 + ph)
            col = tuple(int(BG_TOP[i] + (ACCENT[i] - BG_TOP[i]) * b) for i in range(3))
            r = size * self.k
            d.ellipse([x - r, y - r, x + r, y + r], fill=col)
        return fr

    # ---- scene renderers: each returns a function (frame, local_t, scene_dur) -> None
    def scene_fn(self, sc, dur):
        return getattr(self, "s_" + sc["type"])(sc, dur)

    def s_title(self, sc, dur):
        k, p = self.k, self.post
        tag = text_layer("BOOK REVIEW  ·  NO SPOILERS", self.f_tag, ACCENT, 900 * k)
        title = text_layer(p["title"], self.f_title, TEXT, 900 * k, 1.1)
        author = text_layer(f"by {p['author']}", self.f_sub, MUTED, 900 * k)
        series = text_layer(p.get("series", ""), self.f_sub, ACCENT, 900 * k) if p.get("series") else None
        ch = int(self.H * 0.68)
        cw = int(self.cover.width * ch / self.cover.height)
        cover = self.cover.resize((cw, ch))

        def fn(fr, t, dur):
            x = int(130 * k)
            paste(fr, tag, (x, int(270 * k) + int((1 - ramp(t, 0.2, 0.7)) * 30 * k)), ramp(t, 0.2, 0.7))
            ty = int(330 * k)
            paste(fr, title, (x, ty + int((1 - ramp(t, 0.5, 0.9)) * 40 * k)), ramp(t, 0.5, 0.9))
            ay = ty + title.height + int(20 * k)
            paste(fr, author, (x, ay), ramp(t, 1.1, 0.8))
            if series:
                paste(fr, series, (x, ay + author.height + int(10 * k)), ramp(t, 1.4, 0.8))
            z = 1.0 + 0.05 * (t / dur)
            c = cover.resize((int(cw * z), int(ch * z)))
            cx, cy = self.W - c.width - int(170 * k), (self.H - c.height) // 2
            sh = Image.new("RGBA", (c.width + 40, c.height + 40), (0, 0, 0, 0))
            ImageDraw.Draw(sh).rectangle([20, 30, c.width + 20, c.height + 30], fill=(0, 0, 0, 120))
            paste(fr, sh, (cx - 20, cy - 20), ramp(t, 0.1, 1.0))
            paste(fr, c.convert("RGBA"), (cx, cy + int((1 - ramp(t, 0.1, 1.0)) * 40 * k)), ramp(t, 0.1, 1.0))
        return fn

    def _heading(self, sc):
        return text_layer(sc["heading"], self.f_h1, ACCENT, self.W * 0.8)

    def s_points(self, sc, dur):
        k = self.k
        head = self._heading(sc)
        bullets = [text_layer(b, self.f_body, TEXT, self.W - 460 * k) for b in sc["bullets"]]
        span = max(dur - LEAD - TAIL, 1)
        starts = [LEAD + 0.6 + span * i / max(len(bullets), 1) * 0.9 for i in range(len(bullets))]

        def fn(fr, t, dur):
            paste(fr, head, (int(140 * k), int(150 * k)), ramp(t, 0.2, 0.7))
            y = int(300 * k)
            for b, s in zip(bullets, starts):
                o = ramp(t, s, 0.7)
                if o > 0.02:
                    ImageDraw.Draw(fr).ellipse([140 * k, y + 22 * k, 160 * k, y + 42 * k], fill=tuple(int(BG_BOT[i] + (ACCENT[i] - BG_BOT[i]) * o) for i in range(3)))
                paste(fr, b, (int(190 * k) + int((1 - o) * 40 * k), y), o)
                y += b.height + int(48 * k)
        return fn

    def s_proscons(self, sc, dur):
        k = self.k
        colw = (self.W - 420 * k) / 2
        cols = []
        for key, label, color in (("pros", sc.get("pros_label", "What works"), ACCENT), ("cons", sc.get("cons_label", "What doesn't"), WARN)):
            head = text_layer(label, self.f_h1, color, colw)
            items = [text_layer(b, self.f_body, TEXT, colw - 40 * k) for b in sc[key]]
            cols.append((head, items, color))
        span = max(dur - LEAD - TAIL, 1)
        n = len(cols[0][1]) + len(cols[1][1])
        step = span * 0.9 / max(n, 1)

        def fn(fr, t, dur):
            idx = 0
            for ci, (head, items, color) in enumerate(cols):
                x = int(140 * k + ci * (colw + 140 * k))
                paste(fr, head, (x, int(150 * k)), ramp(t, 0.2 + ci * 0.2, 0.7))
                ImageDraw.Draw(fr).line([x, 150 * k + head.height + 10 * k, x + colw, 150 * k + head.height + 10 * k], fill=color, width=max(2, int(3 * k)))
                y = int(150 * k + head.height + 50 * k)
                for it in items:
                    s = LEAD + 0.4 + idx * step if ci == 0 else LEAD + 0.4 + (len(cols[0][1]) + (idx - len(cols[0][1]))) * step
                    o = ramp(t, s, 0.6)
                    paste(fr, it, (x + int((1 - o) * 30 * k), y), o)
                    y += it.height + int(28 * k)
                    idx += 1
        return fn

    def s_rating(self, sc, dur):
        k, p = self.k, self.post
        rating = int(p["rating"])
        label = text_layer(f"Our rating: {rating} out of 5", self.f_h1, TEXT, self.W * 0.8, align="center")
        gr = text_layer(f"Goodreads readers: {p['goodreads_rating']} / 5", self.f_sub, MUTED, self.W * 0.8, align="center") if p.get("goodreads_rating") else None
        verdict = text_layer(sc["text"], self.f_body, TEXT, self.W - 500 * k, align="center") if sc.get("text") else None

        def fn(fr, t, dur):
            d = ImageDraw.Draw(fr)
            r, gap = 70 * k, 190 * k
            x0 = self.W / 2 - gap * 2
            cy = self.H * 0.36
            for i in range(5):
                s = ramp(t, 0.5 + i * 0.35, 0.45)
                cx = x0 + i * gap
                pts = star_points(cx, cy, r)
                d.polygon(pts, outline=(70, 64, 58), width=max(2, int(4 * k)))
                if i < rating and s > 0:
                    d.polygon(star_points(cx, cy, r * (0.6 + 0.4 * s)), fill=ACCENT)
            paste(fr, label, (int((self.W - label.width) / 2), int(self.H * 0.52)), ramp(t, 0.5 + rating * 0.35, 0.6))
            if gr:
                paste(fr, gr, (int((self.W - gr.width) / 2), int(self.H * 0.52 + label.height + 20 * k)), ramp(t, 2.4, 0.7))
            if verdict:
                paste(fr, verdict, (int((self.W - verdict.width) / 2), int(self.H * 0.52 + label.height + 120 * k)), ramp(t, 3.0, 0.8))
        return fn

    def s_outro(self, sc, dur):
        k = self.k
        a = text_layer(sc.get("heading", "Read the full review"), self.f_h1, TEXT, self.W * 0.8, align="center")
        url = text_layer(SITE["url"].replace("https://", "") + "/", self.f_h1, ACCENT, self.W * 0.9, align="center")
        b = text_layer(sc.get("text", "Honest, balanced, spoiler-free reviews. Subscribe so you don't miss the next one."), self.f_body, MUTED, self.W - 500 * k, align="center")

        def fn(fr, t, dur):
            for layer, y, s in ((a, 0.30, 0.3), (url, 0.43, 0.9), (b, 0.58, 1.5)):
                o = ramp(t, s, 0.8)
                paste(fr, layer, (int((self.W - layer.width) / 2), int(self.H * y + (1 - o) * 30 * k)), o)
        return fn

    # ---- captions + progress bar
    def caption_layers(self, text):
        k = self.k
        out = []
        for s in [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]:
            lay = text_layer(s, self.f_cap, TEXT, self.W - 420 * k, 1.25, align="center")
            box = Image.new("RGBA", (lay.width + int(60 * k), lay.height + int(30 * k)), (10, 9, 8, 190))
            box.paste(lay, (int(30 * k), int(12 * k)), lay)
            out.append((s, box))
        return out


def load_post(slug):
    text = (ROOT / "content/posts" / f"{slug}.md").read_text()
    meta = yaml.safe_load(text.split("---", 2)[1])
    return meta


def get_cover(post, slug, cache):
    path = cache / f"{slug}_cover.jpg"
    if not path.exists() and post.get("cover"):
        try:
            r = requests.get(post["cover"], headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            r.raise_for_status()
            path.write_bytes(r.content)
        except Exception as e:
            print(f"cover download failed: {e}", file=sys.stderr)
    if path.exists():
        try:
            return Image.open(path).convert("RGB")
        except Exception:
            pass
    img = Image.new("RGB", (600, 900), (60, 50, 45))
    ImageDraw.Draw(img).text((40, 400), post["title"], fill=TEXT, font=font("Georgia Bold.ttf", 48))
    return img


def make_thumbnail(post, cover, out):
    W, H = 1280, 720
    img = Image.new("RGB", (W, H), BG_BOT)
    d = ImageDraw.Draw(img)
    for y in range(H):
        f = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(BG_TOP[i] * (1 - f) + BG_BOT[i] * f) for i in range(3)))
    ch = 620
    c = cover.resize((int(cover.width * ch / cover.height), ch))
    img.paste(c, (W - c.width - 70, 50))
    f_big, f_mid, f_small = font("Georgia Bold.ttf", 104), font("Georgia Bold.ttf", 52), font("Georgia Bold.ttf", 34)
    y = 95
    for line in wrap(post["title"].upper(), f_big, W - c.width - 190):
        d.text((60, y), line, font=f_big, fill=TEXT)
        y += 112
    d.text((60, y + 10), "HONEST REVIEW", font=f_mid, fill=ACCENT)
    d.text((60, y + 85), "NO SPOILERS", font=f_small, fill=MUTED)
    for i in range(5):
        pts = star_points(95 + i * 95, y + 190, 38)
        d.polygon(pts, fill=ACCENT) if i < int(post["rating"]) else d.polygon(pts, outline=(90, 84, 78), width=3)
    img.save(out)


def fmt_ts(sec):
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--script")
    ap.add_argument("--res", type=int, default=1080, choices=[360, 720, 1080])
    ap.add_argument("--voice", default=None)
    ap.add_argument("--max-seconds", type=float, default=None)
    a = ap.parse_args()

    post = load_post(a.slug)
    script = json.loads(Path(a.script or ROOT / ".tmp" / f"{a.slug}_video.json").read_text())
    voice = a.voice or script.get("voice", "en-GB-SoniaNeural")
    work = ROOT / ".tmp" / "videos" / a.slug
    cache = ROOT / ".tmp" / "video_cache"
    work.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    cover = get_cover(post, a.slug, cache)

    # 1. narration per scene
    scenes, t0 = [], 0.0
    for sc in script["scenes"]:
        mp3 = synth(sc["narration"], voice, cache)
        dur = LEAD + audio_duration(mp3) + TAIL
        scenes.append({**sc, "mp3": mp3, "dur": dur, "start": t0})
        t0 += dur
    total = t0
    limit = min(total, a.max_seconds) if a.max_seconds else total
    print(f"{len(scenes)} scenes, {total:.1f}s total (rendering {limit:.1f}s) with voice {voice}")

    # 2. audio track: pad each scene's narration, then concatenate
    wavs = []
    for i, sc in enumerate(scenes):
        wav = work / f"scene{i}.wav"
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(sc["mp3"]), "-af", f"adelay={int(LEAD*1000)}|{int(LEAD*1000)},apad", "-t", f"{sc['dur']:.3f}", "-ar", "44100", "-ac", "2", str(wav)], check=True)
        wavs.append(wav)
    listing = work / "audio.txt"
    listing.write_text("".join(f"file '{w}'\n" for w in wavs))
    audio = work / "audio.wav"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(audio)], check=True)

    # 3. frames -> ffmpeg
    vid = Video(a.res, post, script, cover, total)
    fns = [(sc, vid.scene_fn(sc, sc["dur"]), vid.caption_layers(sc["narration"])) for sc in scenes]
    out = work / f"{a.slug}{'_preview' if a.max_seconds else ''}.mp4"
    enc = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{vid.W}x{vid.H}", "-r", str(FPS), "-i", "-", "-i", str(audio),
                            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-t", f"{limit:.3f}", "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
    n = int(limit * FPS)
    bar_h = max(3, int(6 * vid.k))
    for i in range(n):
        t = i / FPS
        si = max(j for j, s in enumerate(scenes) if s["start"] <= t)
        sc, fn, caps = fns[si]
        lt = t - sc["start"]
        fr = vid.frame(t)
        fn(fr, lt, sc["dur"])
        # caption timed proportionally to sentence length across the narration window
        nar_t = lt - LEAD
        total_chars = sum(len(s) for s, _ in caps) or 1
        nar_len = sc["dur"] - LEAD - TAIL
        acc = 0
        for s, box in caps:
            s0, s1 = acc / total_chars * nar_len, (acc + len(s)) / total_chars * nar_len
            acc += len(s)
            if s0 <= nar_t < s1:
                paste(fr, box, ((vid.W - box.width) // 2, vid.H - box.height - int(70 * vid.k)), min(1, (nar_t - s0) / 0.2 + 0.2))
                break
        ImageDraw.Draw(fr).rectangle([0, vid.H - bar_h, int(vid.W * t / total), vid.H], fill=ACCENT)
        enc.stdin.write(fr.tobytes())
        if i % (FPS * 10) == 0:
            print(f"  {t:5.0f}s / {limit:.0f}s", flush=True)
    enc.stdin.close()
    if enc.wait() != 0:
        sys.exit("ffmpeg failed")
    print(out)

    if a.max_seconds:
        return
    # 4. thumbnail + YouTube metadata
    thumb = work / f"{a.slug}_thumbnail.png"
    make_thumbnail(post, cover, thumb)
    chapters = "\n".join(f"{fmt_ts(s['start'])} {s.get('chapter') or s.get('heading') or s['type'].title()}" for s in scenes)
    tags = list(dict.fromkeys(["book review", "spoiler free book review", post["title"], post["author"]] + post.get("genres", []) + post.get("tags", [])))
    meta = {
        "title": f"{post['title']} Review (No Spoilers) | {SITE['name']}"[:100],
        "description": f"{post['title']} by {post['author']}: an honest, balanced and completely spoiler-free review.\n\n"
                       f"Our rating: {post['rating']}/5" + (f" | Goodreads: {post['goodreads_rating']}/5" if post.get("goodreads_rating") else "") +
                       f"\n\nRead the full written review: {SITE['url']}/books/{a.slug}.html\n\nChapters:\n{chapters}\n\n"
                       f"Ratings and publication details from Goodreads and Open Library. Book cover shown for review purposes.\n\n#{' #'.join(t.replace(' ', '') for t in tags[:5])}",
        "tags": tags[:15],
        "category": "Education",
        "privacy": "private",
        "video": str(out),
        "thumbnail": str(thumb),
    }
    (work / f"{a.slug}_youtube.json").write_text(json.dumps(meta, indent=2))
    print(thumb)
    print(work / f"{a.slug}_youtube.json")


if __name__ == "__main__":
    main()
