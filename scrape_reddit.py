"""
scrape_reddit.py — Fetch Reddit threads into clean .txt files for the corpus.

Uses Reddit's OFFICIAL OAuth API in read-only ("userless") mode. Reddit now
blocks unauthenticated scraping, so you need free API credentials — see
.env.example for the 2-minute setup. Standard library only (works on 3.14).

Usage:
    1. Put REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET in .env  (see .env.example)
    2. Paste your chosen thread URLs into THREAD_URLS below.
    3. Run:  python scrape_reddit.py
    4. One clean .txt per thread lands in documents/.

This is a low-volume, one-time educational pull. It sleeps between requests.
"""

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

# --- Configure here -------------------------------------------------------

# Paste the full thread URLs you picked from r/NEU etc. (one per line).
THREAD_URLS = [
    # "https://www.reddit.com/r/NEU/comments/abc123/best_cs_professors/",
    # "https://www.reddit.com/r/NEU/comments/def456/how_hard_is_cs3000/",
]

# Filters to keep the corpus clean.
MIN_COMMENT_SCORE = 1      # drop downvoted/zero comments
MIN_COMMENT_CHARS = 20     # drop "lol", "this", one-word replies
SKIP_AUTHORS = {"AutoModerator"}

OUTPUT_DIR = Path(__file__).parent / "documents"
REQUEST_DELAY_SECONDS = 2.0
USER_AGENT = "python:ai201-unofficial-guide:v1.0 (educational project)"

# --- Credentials ----------------------------------------------------------


def load_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


ENV = load_env(Path(__file__).parent / ".env")
CLIENT_ID = ENV.get("REDDIT_CLIENT_ID", "")
CLIENT_SECRET = ENV.get("REDDIT_CLIENT_SECRET", "")

# --- Reddit API plumbing --------------------------------------------------


def get_token() -> str:
    if not CLIENT_ID or not CLIENT_SECRET or "your_client" in CLIENT_ID:
        raise SystemExit(
            "Missing Reddit credentials. Add REDDIT_CLIENT_ID and "
            "REDDIT_CLIENT_SECRET to .env (see .env.example for setup)."
        )
    data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    req = urllib.request.Request(
        "https://www.reddit.com/api/v1/access_token",
        data=data,
        headers={"User-Agent": USER_AGENT},
    )
    # Basic auth with client id/secret.
    import base64

    auth = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    req.add_header("Authorization", f"Basic {auth}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["access_token"]


def thread_id_from_url(url: str) -> str:
    # .../comments/<id>/<slug>/ -> <id>
    m = re.search(r"/comments/([a-z0-9]+)", url)
    if not m:
        raise ValueError(f"Could not parse thread id from {url!r}")
    return m.group(1)


def fetch_thread(token: str, thread_id: str) -> list:
    url = f"https://oauth.reddit.com/comments/{thread_id}?limit=500&depth=10&raw_json=1"
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Authorization": f"bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


# --- Parsing & formatting -------------------------------------------------


def walk_comments(children: list, depth: int, out: list) -> None:
    for child in children:
        if child.get("kind") != "t1":  # skip "more" / non-comment nodes
            continue
        c = child["data"]
        body = (c.get("body") or "").strip()
        author = c.get("author") or "[unknown]"
        score = c.get("score", 0)

        keep = (
            body
            and body not in ("[deleted]", "[removed]")
            and author not in SKIP_AUTHORS
            and score >= MIN_COMMENT_SCORE
            and len(body) >= MIN_COMMENT_CHARS
        )
        if keep:
            indent = "  " * depth
            body_indented = body.replace("\n", f"\n{indent}  ")
            out.append(f"{indent}- (+{score}) {body_indented}")

        replies = c.get("replies")
        if isinstance(replies, dict):
            walk_comments(replies["data"]["children"], depth + 1, out)


def format_thread(payload: list) -> tuple[str, str]:
    post = payload[0]["data"]["children"][0]["data"]
    title = post.get("title", "Untitled")
    subreddit = post.get("subreddit_name_prefixed", "")
    selftext = (post.get("selftext") or "").strip()
    score = post.get("score", 0)
    permalink = "https://www.reddit.com" + post.get("permalink", "")

    lines = [
        title,
        f"Source: Reddit {subreddit}  (post score +{score})",
        f"URL: {permalink}",
        "",
    ]
    if selftext and selftext not in ("[deleted]", "[removed]"):
        lines += ["Original post:", selftext, ""]
    lines += ["=" * 60, "COMMENTS", "=" * 60, ""]

    comments: list[str] = []
    walk_comments(payload[1]["data"]["children"], 0, comments)
    lines += comments

    return title, "\n".join(lines) + "\n"


def safe_filename(title: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")[:50]
    return f"reddit_{slug}.txt"


# --- Main -----------------------------------------------------------------


def main() -> None:
    if not THREAD_URLS:
        raise SystemExit("No thread URLs configured. Add some to THREAD_URLS.")
    OUTPUT_DIR.mkdir(exist_ok=True)
    print("Authenticating with Reddit...")
    token = get_token()

    for url in THREAD_URLS:
        try:
            tid = thread_id_from_url(url)
            payload = fetch_thread(token, tid)
            title, text = format_thread(payload)
        except Exception as e:
            print(f"  SKIPPED {url} — {type(e).__name__}: {e}")
            continue

        n_comments = text.count("\n- ") + text.count("\n  - ")
        out_path = OUTPUT_DIR / safe_filename(title)
        out_path.write_text(text, encoding="utf-8")
        print(f"  -> {out_path.name}  (~{n_comments} kept comments)")
        time.sleep(REQUEST_DELAY_SECONDS)

    print("\nDone.")


if __name__ == "__main__":
    main()
