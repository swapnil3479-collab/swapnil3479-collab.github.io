"""Render content/posts/*.md (and optionally drafts) into docs/ for GitHub Pages.

Usage: build_site.py [--drafts]   (--drafts builds a local preview including drafts; never deploy that)
"""
import argparse, shutil
from pathlib import Path
import markdown, yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"


def load(path, draft):
    text = path.read_text()
    _, fm, body = text.split("---", 2)
    meta = yaml.safe_load(fm)
    meta["html"] = markdown.markdown(body.strip(), extensions=["extra"])
    meta["draft"] = draft
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drafts", action="store_true")
    a = ap.parse_args()
    posts = [load(p, False) for p in (ROOT / "content/posts").glob("*.md")]
    if a.drafts:
        posts += [load(p, True) for p in (ROOT / "content/drafts").glob("*.md")]
    posts.sort(key=lambda p: str(p["date"]), reverse=True)
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "books").mkdir(parents=True)
    (OUT / ".nojekyll").touch()
    shutil.copy(ROOT / "templates/style.css", OUT / "style.css")
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape())
    genres = sorted({g for p in posts for g in p.get("genres", [])})
    (OUT / "index.html").write_text(env.get_template("index.html").render(posts=posts, genres=genres, root=""))
    for p in posts:
        (OUT / "books" / f"{p['slug']}.html").write_text(env.get_template("post.html").render(p=p, root="../"))
    print(f"Built {len(posts)} post(s) -> {OUT}")


if __name__ == "__main__":
    main()
