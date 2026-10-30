# Write a Book Post

## Objective
Given a book name, produce a spoiler-free summary and a balanced critical review, saved as a **draft** post.

## Inputs
- Book title (required); author (optional, use it if the title is ambiguous)
- Optional: the user's own rating or notes

## Steps
1. **Metadata:** `.venv/bin/python tools/fetch_book_metadata.py "<title>" "<author>"`. Pull in Open Library and Google Books results. If results disagree or several editions/books match, ask the user which one.
2. **Goodreads:** Goodreads has no public API and its terms forbid scraping. Use WebSearch/WebFetch to read the public Goodreads page for the book (average rating, rating count, common praise and complaints). Record `goodreads_rating` and `goodreads_url`. If it can't be fetched, leave both blank and say so. Never invent a rating.
3. **Write the body** to `.tmp/<slug>.md` using the structure below.
4. **Spoiler check (mandatory):** re-read the Summary and Review and confirm no twist, death, betrayal, reveal or ending is stated or hinted. For a sequel, do not spoil earlier books either. Fix, then proceed.
5. **Write `.tmp/<slug>.json`** metadata (title, author, year, pages, genres, tags, cover, rating 1-5 integer, goodreads_rating, goodreads_url, slug). `genres[0]` is the primary genre and the home-page section the book is filed under (use broad names such as Fantasy, Science Fiction, Mystery, Romance, Non-Fiction, Historical Fiction; reuse existing ones so sections stay consistent). `tags` are 3-6 short Title Case descriptors (audience, themes, tropes, format such as Young Adult, Assassins, Prequel, Series Starter); reuse existing tags where they fit. Tags are clickable on review pages and appear as filter buttons on the home page.
6. **Save:** `.venv/bin/python tools/save_post.py --meta .tmp/<slug>.json --body .tmp/<slug>.md` (publishes to `content/posts/`; add `--draft` only if the user asks to hold a post back).
7. **Deploy:** `.venv/bin/python tools/deploy_site.py "Add <title> review"`, then poll the Pages build until it is `built` for the new commit and the page returns 200.
8. Tell the user the live URL, rating and anything notable (sources that failed, uncertainty).

## Body structure
```
## Summary (spoiler-free)
Premise and setup only: the first act at most. No twists or ending. ~150-200 words.

## Review
Balanced critic: what works, what doesn't, with specific reasons. Cover writing style,
pacing, characters, themes, and how it compares to Goodreads sentiment if relevant. ~350-500 words.

## Who should read it
Who will love it and who should skip it.

## Verdict
One short paragraph and the star rating.
```

## Rules
- **No approval step.** The user waived draft approval on 2026-10-30: publish and deploy directly. The spoiler check and originality rules below are therefore mandatory, since nothing else catches errors before the post is live.
- Balanced means every review names real strengths and real weaknesses; no gushing, no hit pieces.
- Facts (year, pages, plot setup) come from the tools, not memory. If a book is obscure and sources are thin, say so and ask rather than guess.
- Don't quote long passages from the book.
- **Originality:** Use several sources (Open Library, Google Books, Goodreads, Wikipedia, at least one independent review) for facts, structure and general reader sentiment only. Never paste or lightly reword a reviewer's sentences, and don't quote reviews. Cite rating numbers, not text.
- **Sequels and prequels:** don't reveal earlier books' endings. Publisher blurbs for later books often do, so write the summary from scratch.

## Drafts (optional) & publishing
1. Only if the user asks for a draft: `--draft` saves to `content/drafts/`; later run `.venv/bin/python tools/approve_post.py <slug>` to publish it.
2. Preview locally (optional): `.venv/bin/python tools/build_site.py --drafts` then open `docs/index.html`
3. Deploy: `.venv/bin/python tools/deploy_site.py "Add <title>"`. This rebuilds without drafts, commits and pushes. GitHub Pages serves the `docs/` folder from `main`.

## One-time GitHub setup
Create a repo, `git init`, add the remote, push `main`, then in Settings → Pages choose "Deploy from branch", `main`, `/docs`.

## Learnings
- Google Books returns 429 without an API key (seen on the first real run). Set `GOOGLE_BOOKS_API_KEY` in `.env`; until then Open Library plus the Goodreads page are enough.
- Open Library search can return box sets and omnibuses with absurd page counts and few ratings. Use the entry whose title exactly matches the book.
- WebSearch limited to goodreads.com returns the rating and count; WebFetch on the Goodreads book page gives the blurb and common praise/complaints.
