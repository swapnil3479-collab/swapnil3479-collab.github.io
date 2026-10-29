"""Move an approved draft into content/posts/. Usage: approve_post.py <slug>"""
import shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) != 2:
    sys.exit(__doc__)
src = ROOT / "content/drafts" / f"{sys.argv[1]}.md"
if not src.exists():
    sys.exit(f"No draft named {sys.argv[1]}")
dst = ROOT / "content/posts" / src.name
shutil.move(src, dst)
print(dst)
