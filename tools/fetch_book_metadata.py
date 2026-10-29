"""Fetch book metadata from Open Library and Google Books; print merged JSON.

Usage: fetch_book_metadata.py "Title" ["Author"]
Goodreads has no public API; ratings are read separately (see workflows/write_book_post.md).
"""
import json, os, sys
import requests
from dotenv import load_dotenv

load_dotenv()
TIMEOUT = 15


def open_library(title, author):
    params = {"title": title, "limit": 3,
              "fields": "key,title,author_name,first_publish_year,number_of_pages_median,subject,cover_i,ratings_average,ratings_count"}
    if author:
        params["author"] = author
    r = requests.get("https://openlibrary.org/search.json", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("docs", [])


def google_books(title, author):
    q = f"intitle:{title}" + (f"+inauthor:{author}" if author else "")
    params = {"q": q, "maxResults": 3}
    if os.getenv("GOOGLE_BOOKS_API_KEY"):
        params["key"] = os.environ["GOOGLE_BOOKS_API_KEY"]
    r = requests.get("https://www.googleapis.com/books/v1/volumes", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for item in r.json().get("items", []):
        v = item.get("volumeInfo", {})
        out.append({
            "title": v.get("title"), "subtitle": v.get("subtitle"),
            "authors": v.get("authors"), "published": v.get("publishedDate"),
            "pages": v.get("pageCount"), "categories": v.get("categories"),
            "description": v.get("description"),
            "average_rating": v.get("averageRating"), "ratings_count": v.get("ratingsCount"),
            "cover": (v.get("imageLinks") or {}).get("thumbnail"),
            "isbn": [i["identifier"] for i in v.get("industryIdentifiers", [])],
        })
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    title = sys.argv[1]
    author = sys.argv[2] if len(sys.argv) > 2 else None
    result = {"query": {"title": title, "author": author}}
    for name, fn in (("open_library", open_library), ("google_books", google_books)):
        try:
            result[name] = fn(title, author)
        except Exception as e:  # one source failing must not block the other
            result[name] = {"error": str(e)}
    for d in result["open_library"] if isinstance(result["open_library"], list) else []:
        if d.get("cover_i"):
            d["cover_url"] = f"https://covers.openlibrary.org/b/id/{d['cover_i']}-L.jpg"
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
