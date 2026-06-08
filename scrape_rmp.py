"""
scrape_rmp.py — Fetch Rate My Professors reviews into clean .txt files.

Talks to RMP's GraphQL API directly using only the Python standard library
(no third-party dependencies, works on Python 3.14).

Usage:
    1. Edit SCHOOL_NAME and PROFESSORS below.
    2. Run:  python scrape_rmp.py
    3. One clean .txt per professor lands in documents/.

Note: This is a low-volume, one-time educational pull for an academic project.
It sleeps between requests to stay polite. Don't run it in a loop or at scale.
"""

import json
import re
import time
import urllib.request
from pathlib import Path

# --- Configure here -------------------------------------------------------

SCHOOL_NAME = "Northeastern University"

# List the professors you want. Add an optional "department" hint to pick the
# right person when several share a name (e.g. three "Zhang"s). The hint is
# matched case-insensitively as a substring of RMP's department field.
PROFESSORS = [
    {"name": "Hongyang Zhang", "department": "Computer Science"},
    {"name": "Kaan Onarlioglu", "department": "Computer Science"},
    {"name": "Lucia Nunez", "department": "Computer Science"},
    {"name": "Karl Lieberherr", "department": "Computer Science"},
    {"name": "Gregory Aloupis", "department": "Computer Science"},
    {"name": "Mark Fontenot", "department": "Computer Science"},
    {"name": "Justin Wang", "department": "Computer Science"},
    {"name": "Joydeep Mitra", "department": "Computer Science"},
    {"name": "Andrew van der Poel", "department": "Computer Science"},
    {"name": "Akshar Varma", "department": "Computer Science"},
]

OUTPUT_DIR = Path(__file__).parent / "documents"
REQUEST_DELAY_SECONDS = 1.5  # be polite between requests

# --- RMP API plumbing -----------------------------------------------------

URL = "https://www.ratemyprofessors.com/graphql"
HEADERS = {
    # "test:test" base64 — the public token RMP's own front end ships with.
    "Authorization": "Basic dGVzdDp0ZXN0",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0",
}


def gql(query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(URL, data=payload, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]


def find_school_id(name: str) -> str:
    query = """query($q:SchoolSearchQuery!){
      newSearch{schools(query:$q){edges{node{id name}}}}}"""
    edges = gql(query, {"q": {"text": name}})["newSearch"]["schools"]["edges"]
    if not edges:
        raise SystemExit(f"No school found matching {name!r}")
    # Prefer an exact (case-insensitive) name match, else the first result.
    for e in edges:
        if e["node"]["name"].lower() == name.lower():
            return e["node"]["id"]
    print(f"  (no exact school match; using {edges[0]['node']['name']!r})")
    return edges[0]["node"]["id"]


def find_teacher(name: str, school_id: str, dept_hint: str | None) -> dict:
    query = """query($q:TeacherSearchQuery!){
      newSearch{teachers(query:$q){edges{node{
        id firstName lastName department
        avgRating avgDifficulty wouldTakeAgainPercent numRatings
      }}}}}"""
    edges = gql(query, {"q": {"text": name, "schoolID": school_id}})[
        "newSearch"
    ]["teachers"]["edges"]
    nodes = [e["node"] for e in edges]
    if not nodes:
        raise LookupError(f"No professor found matching {name!r}")

    # Filter to the name we actually asked for (search is fuzzy).
    name_parts = name.lower().split()
    nodes = [
        n
        for n in nodes
        if all(
            p in f"{n['firstName']} {n['lastName']}".lower() for p in name_parts
        )
    ] or nodes

    if dept_hint:
        dept_matches = [
            n for n in nodes if dept_hint.lower() in (n["department"] or "").lower()
        ]
        if dept_matches:
            nodes = dept_matches

    # Among remaining candidates, pick the one with the most ratings.
    return max(nodes, key=lambda n: n["numRatings"])


def fetch_ratings(teacher_id: str) -> dict:
    query = """query($id:ID!){node(id:$id){... on Teacher{
      firstName lastName department
      avgRating avgDifficulty wouldTakeAgainPercent numRatings
      ratings(first:1000){edges{node{
        class comment date difficultyRating clarityRating
        grade wouldTakeAgain attendanceMandatory isForCredit ratingTags
      }}}}}}"""
    return gql(query, {"id": teacher_id})["node"]


# --- Formatting -----------------------------------------------------------


def clean_date(raw: str) -> str:
    # "2026-05-24 15:50:25 +0000 UTC" -> "2026-05-24"
    return raw.split(" ", 1)[0] if raw else ""


def would_take_again(value) -> str:
    if value == 1:
        return "Yes"
    if value == 0:
        return "No"
    return "N/A"


def format_professor(t: dict) -> str:
    lines = []
    full_name = f"{t['firstName']} {t['lastName']}"
    lines.append(full_name)
    lines.append(f"Department: {t['department']}")
    lines.append(f"Overall Quality: {t['avgRating']} / 5 (based on {t['numRatings']} ratings)")
    lines.append(f"Average Difficulty: {t['avgDifficulty']} / 5")
    wta = t.get("wouldTakeAgainPercent")
    lines.append(f"Would Take Again: {round(wta)}%" if wta and wta >= 0 else "Would Take Again: N/A")
    lines.append("")
    lines.append("=" * 60)
    lines.append("REVIEWS")
    lines.append("=" * 60)

    for edge in t["ratings"]["edges"]:
        r = edge["node"]
        lines.append("")
        lines.append(f"Course: {r['class']}    Date: {clean_date(r['date'])}")
        lines.append(
            f"Quality: {r['clarityRating']}/5    "
            f"Difficulty: {r['difficultyRating']}/5    "
            f"Grade: {r['grade'] or 'N/A'}    "
            f"Would Take Again: {would_take_again(r['wouldTakeAgain'])}"
        )
        tags = (r.get("ratingTags") or "").replace("--", ", ").strip(", ")
        if tags:
            lines.append(f"Tags: {tags}")
        comment = (r.get("comment") or "").strip()
        lines.append(f"Review: {comment}")

    return "\n".join(lines) + "\n"


def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") + ".txt"


# --- Main -----------------------------------------------------------------


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    print(f"Looking up school: {SCHOOL_NAME}")
    school_id = find_school_id(SCHOOL_NAME)

    for entry in PROFESSORS:
        name = entry["name"]
        dept = entry.get("department")
        print(f"\nFetching: {name}" + (f" ({dept})" if dept else ""))
        try:
            teacher_stub = find_teacher(name, school_id, dept)
            teacher = fetch_ratings(teacher_stub["id"])
        except LookupError as e:
            print(f"  SKIPPED — {e}")
            continue

        n_reviews = len(teacher["ratings"]["edges"])
        out_path = OUTPUT_DIR / safe_filename(
            f"{teacher['firstName']} {teacher['lastName']}"
        )
        out_path.write_text(format_professor(teacher), encoding="utf-8")
        print(f"  -> {out_path.name}  ({n_reviews} reviews, dept: {teacher['department']})")
        time.sleep(REQUEST_DELAY_SECONDS)

    print("\nDone.")


if __name__ == "__main__":
    main()
