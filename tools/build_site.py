"""Render content/posts/*.md (and optionally drafts) into docs/ for GitHub Pages.

Usage: build_site.py [--drafts]   (--drafts builds a local preview including drafts; never deploy that)
Also writes sitemap.xml, robots.txt and feed.xml. Config lives in SITE below.
"""
import argparse, datetime, html, re, shutil
from email.utils import format_datetime
from pathlib import Path
import markdown, yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"
SITE = {
    "name": "The Honest Shelf",
    "tagline": "Balanced, spoiler-free book reviews.",
    "url": "https://swapnil3479-collab.github.io",  # no trailing slash; change if a custom domain is added
    "newsletter_url": "",  # paste a Buttondown/Mailchimp/Formspree sign-up URL to show a subscribe box
}


def describe(p):
    """Meta description: first paragraph of the Summary section, else the first paragraph, trimmed to ~155 chars."""
    m = re.search(r"<h2>Summary.*?</h2>\s*<p>(.*?)</p>", p["html"], re.S) or re.search(r"<p>(.*?)</p>", p["html"], re.S)
    text = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))) if m else p["title"]
    text = " ".join(text.split())
    if len(text) > 155:
        text = text[:152].rsplit(" ", 1)[0] + "..."
    return f"{p['title']} by {p['author']}: spoiler-free summary and honest review. {text}"[:300]


def load(path, draft):
    _, fm, body = path.read_text().split("---", 2)
    meta = yaml.safe_load(fm)
    meta["html"] = markdown.markdown(body.strip(), extensions=["extra"])
    meta["draft"] = draft
    meta["date"] = str(meta["date"])
    meta["description"] = meta.get("description") or describe(meta)
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drafts", action="store_true")
    a = ap.parse_args()
    posts = [load(p, False) for p in (ROOT / "content/posts").glob("*.md")]
    if a.drafts:
        posts += [load(p, True) for p in (ROOT / "content/drafts").glob("*.md")]
    posts.sort(key=lambda p: p["date"], reverse=True)
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "books").mkdir(parents=True)
    (OUT / ".nojekyll").touch()
    shutil.copy(ROOT / "templates/style.css", OUT / "style.css")
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape())
    env.filters["xmlstr"] = lambda s: html.escape(str(s), quote=True)
    base = SITE["url"]
    (OUT / "index.html").write_text(env.get_template("index.html").render(
        posts=posts, root="", site=SITE, page_url=f"{base}/", description=f"{SITE['name']}: {SITE['tagline']} Reviews of fantasy and fiction with honest ratings and no plot twists given away."))
    for p in posts:
        (OUT / "books" / f"{p['slug']}.html").write_text(env.get_template("post.html").render(
            p=p, root="../", site=SITE, page_url=f"{base}/books/{p['slug']}.html", description=p["description"]))
    live = [p for p in posts if not p["draft"]]
    today = datetime.date.today().isoformat()
    urls = [(f"{base}/", today)] + [(f"{base}/books/{p['slug']}.html", p["date"]) for p in live]
    (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc><lastmod>{d}</lastmod></url>\n" for u, d in urls) + "</urlset>\n")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {base}/sitemap.xml\n")
    (OUT / "feed.xml").write_text(env.get_template("feed.xml").render(
        posts=live[:20], site=SITE, build=format_datetime(datetime.datetime.now(datetime.timezone.utc)),
        rfc=lambda d: format_datetime(datetime.datetime.fromisoformat(d).replace(tzinfo=datetime.timezone.utc))))
    print(f"Built {len(posts)} post(s) -> {OUT}")


if __name__ == "__main__":
    main()
