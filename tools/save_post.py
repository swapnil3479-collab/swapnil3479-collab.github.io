"""Save a post as Markdown with front matter.

Usage: save_post.py --meta meta.json --body body.md [--draft]
meta.json keys: title, author, slug (optional), year, genres[] (FIRST one is the section it is filed under on the home page), tags[] (short, Title Case, e.g. Assassins, Prequel), rating (1-5, our review),
  goodreads_rating, goodreads_url, cover, pages, tagline
Posts publish directly to content/posts/ (the user waived draft approval on 2026-10-30).
Pass --draft to hold a post back in content/drafts/ instead.
"""
import argparse, datetime, json, re, sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
DRAFTS, POSTS = ROOT / "content/drafts", ROOT / "content/posts"


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta", required=True)
    ap.add_argument("--body", required=True)
    ap.add_argument("--draft", action="store_true")
    a = ap.parse_args()
    meta = json.loads(Path(a.meta).read_text())
    body = Path(a.body).read_text().strip()
    meta["slug"] = meta.get("slug") or slugify(meta["title"])
    meta["date"] = meta.get("date") or datetime.date.today().isoformat()
    DRAFTS.mkdir(parents=True, exist_ok=True); POSTS.mkdir(parents=True, exist_ok=True)
    dest = DRAFTS if a.draft else POSTS
    path = dest / f"{meta['slug']}.md"
    path.write_text("---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True) + "---\n\n" + body + "\n")
    print(path)


if __name__ == "__main__":
    main()
