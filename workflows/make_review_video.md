# Make a Review Video (YouTube)

## Objective
Turn a published review into a short, animated, narrated, spoiler-free video plus a thumbnail and ready-to-use YouTube metadata. Nothing is uploaded automatically.

## Inputs
- The slug of a published review in `content/posts/` (the review is the single source of truth for facts and opinion).

## Requirements (one-time)
- `brew install ffmpeg` (the pip-bundled ffmpeg hung on this Mac).
- `.venv/bin/pip install -r requirements.txt` (Pillow, edge-tts, etc.).
- Narration uses edge-tts (free Microsoft online voices, needs internet; falls back to macOS `say`). Default voice `en-GB-RyanNeural` (male; other male options: en-US-AndrewNeural, en-US-GuyNeural, en-GB-ThomasNeural); change with `--voice`.

## Steps
1. **Write the scene script** to `.tmp/<slug>_video.json`. Condense the published review; never add new facts, and apply the same spoiler rules as the review (for sequels, nothing that reveals earlier books). Target 2-3 minutes (~300-450 spoken words). Format:
   ```json
   {"voice": "en-GB-RyanNeural", "scenes": [
     {"type": "title",    "chapter": "Intro",   "narration": "..."},
     {"type": "points",   "chapter": "Setup",   "heading": "The setup", "bullets": ["short line", "..."], "narration": "..."},
     {"type": "proscons", "chapter": "Review",  "pros": ["..."], "cons": ["..."], "narration": "..."},
     {"type": "rating",   "chapter": "Verdict", "text": "one-line verdict", "narration": "..."},
     {"type": "outro",    "chapter": "Full review", "heading": "Read the full review", "narration": "..."}
   ]}
   ```
   - Bullets are 4-10 words, 3-4 per scene (4 max per column in proscons). Write numbers as words in `narration` (e.g. "four point one eight") so TTS reads them well.
   - Rating, Goodreads score, cover, title and series come from the post's front matter.
2. **Preview:** `.venv/bin/python tools/make_video.py <slug> --res 360 --max-seconds 25` (fast, low-res). Check frames and audio.
3. **Full render:** `.venv/bin/python tools/make_video.py <slug> --res 1080`. Output goes to `.tmp/videos/<slug>/`: `<slug>.mp4`, `<slug>_thumbnail.png`, `<slug>_youtube.json` (title, description with chapters, tags; privacy defaults to private).
4. Report the paths and duration. Do **not** upload.

## Rules
- Same originality rules as the written review: no quoting reviews, no copying text.
- The cover image appears for review purposes; the description says so.
- No background music unless the user supplies a royalty-free track (copyright claims).
- Upload to YouTube is a separate, user-approved step (needs Google OAuth and publishes publicly). Not built yet.

## Learnings
- imageio-ffmpeg's bundled binary hung at launch on macOS after the first run; use system ffmpeg.
- Python.org builds lack SSL certs for urllib; use `requests` for downloads.
- Rendering is CPU-bound in Pillow, roughly real-time at 720p; do a `--max-seconds` preview before a full render.
- Long commands get moved to the background after 120 s: run renders in the background and watch the log instead of waiting.
