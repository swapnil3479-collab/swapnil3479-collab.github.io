"""Commit and push to GitHub (Pages serves /docs on main). Usage: deploy_site.py "message"
Rebuilds first without drafts so drafts can never be published by accident."""
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
msg = sys.argv[1] if len(sys.argv) > 1 else "Update site"
run = lambda *c: subprocess.run(c, cwd=ROOT, check=True)
run(sys.executable, "tools/build_site.py")
run("git", "add", "content/posts", "content/series", "docs", "templates", "tools", "workflows", "CLAUDE.md", "requirements.txt", ".gitignore")
if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode:
    run("git", "commit", "-m", msg)
run("git", "push", "origin", "main")
