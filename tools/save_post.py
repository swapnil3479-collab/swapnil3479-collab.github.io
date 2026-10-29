"""Save a post as Markdown with front matter.

Usage: save_post.py --meta meta.json --body body.md [--publish]
meta.json keys: title, author, slug (optional), year, genres[], rating (1-5, our review),
  goodreads_rating, goodreads_url, cover, pages, tagline
Rule: the first 10 posts are ALWAYS saved as drafts; --publish only works after that.
"""
import argparse, datetime, json, re, sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
DRAFTS, POSTS = ROOT / "content/drafts", ROOT / "content/posts"
DRAFT_ONLY_LIMIT = 10


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta", required=True)
    ap.add_argument("--body", required=True)
    ap.add_argument("--publish", action="store_true")
    a = ap.parse_args()
    meta = json.loads(Path(a.meta).read_text())
    body = Path(a.body).read_text().strip()
    meta["slug"] = meta.get("slug") or slugify(meta["title"])
    meta["date"] = meta.get("date") or datetime.date.today().isoformat()
    DRAFTS.mkdir(parents=True, exist_ok=True); POSTS.mkdir(parents=True, exist_ok=True)
    total = len(list(DRAFTS.glob("*.md"))) + len(list(POSTS.glob("*.md")))
    if a.publish and total < DRAFT_ONLY_LIMIT:
        print(f"Refusing --publish: only {total} posts so far; the first {DRAFT_ONLY_LIMIT} stay drafts.", file=sys.stderr)
    dest = POSTS if (a.publish and total >= DRAFT_ONLY_LIMIT) else DRAFTS
    path = dest / f"{meta['slug']}.md"
    path.write_text("---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True) + "---\n\n" + body + "\n")
    print(path)


if __name__ == "__main__":
    main()
