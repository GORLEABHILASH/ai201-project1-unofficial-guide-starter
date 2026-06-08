"""
ingest.py — Milestone 3: Document ingestion and chunking.

Reads the Rate My Professors .txt files in documents/ (produced by
scrape_rmp.py) and turns them into one chunk per student review, each prefixed
with the professor, course, and ratings so the chunk stays attributable and
searchable after it is separated from its source file.

Run directly to verify:  python ingest.py
"""

import re
from pathlib import Path

DOCUMENTS_DIR = Path(__file__).parent / "documents"

# Abbreviate the long department name for the chunk prefix; pass others through.
DEPT_ABBR = {"Computer Science": "CS"}

# --- Ingestion ------------------------------------------------------------


def parse_review_block(block: str) -> dict | None:
    """Parse one review block into structured fields. Returns None if it isn't
    a valid review (no Course line)."""
    course = re.search(r"Course:\s*(\S+)", block)
    if not course:
        return None

    quality = re.search(r"Quality:\s*(\d+)/5", block)
    difficulty = re.search(r"Difficulty:\s*(\d+)/5", block)
    grade = re.search(r"Grade:\s*(.+?)\s+Would Take Again", block)

    # Review text is everything after the "Review:" marker (may span lines).
    review_match = re.search(r"Review:\s*(.*)", block, re.DOTALL)
    review_text = review_match.group(1).strip() if review_match else ""

    return {
        # Uppercase so "cs1800" and "CS1800" become one course for filtering.
        "course": course.group(1).upper(),
        "quality": int(quality.group(1)) if quality else None,
        "difficulty": int(difficulty.group(1)) if difficulty else None,
        "grade": grade.group(1).strip() if grade else "N/A",
        "review": review_text,
    }


def load_documents(docs_dir: Path = DOCUMENTS_DIR) -> list[dict]:
    """Read every .txt file in docs_dir and parse it into a header plus a list
    of individual reviews."""
    documents = []
    for path in sorted(docs_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8")

        # Split the file into the header (above REVIEWS) and the reviews body.
        parts = re.split(r"=+\s*\nREVIEWS\s*\n=+", text, maxsplit=1)
        header_text = parts[0]
        body = parts[1] if len(parts) > 1 else ""

        # Header: professor is the first non-empty line; department is labeled.
        header_lines = [ln for ln in header_text.splitlines() if ln.strip()]
        professor = header_lines[0].strip() if header_lines else path.stem
        dept_match = re.search(r"Department:\s*(.+)", header_text)
        department = dept_match.group(1).strip() if dept_match else "Unknown"

        # Body: a new review begins at each line starting with "Course:".
        reviews = []
        current: list[str] = []
        for line in body.splitlines():
            if line.startswith("Course:"):
                if current:
                    parsed = parse_review_block("\n".join(current))
                    if parsed:
                        reviews.append(parsed)
                current = [line]
            elif current:
                current.append(line)
        if current:  # flush the last block
            parsed = parse_review_block("\n".join(current))
            if parsed:
                reviews.append(parsed)

        documents.append(
            {
                "professor": professor,
                "department": department,
                "source_file": path.name,
                "reviews": reviews,
            }
        )
    return documents


# --- Chunking -------------------------------------------------------------


def chunk_text(documents: list[dict]) -> list[tuple[str, dict]]:
    """Turn loaded documents into (chunk_text, metadata) pairs — one per review.

    Each chunk is prefixed with professor, department, course, and ratings so
    it remains attributable; the same fields are also stored as metadata for
    exact filtering and citation in later milestones.
    """
    chunks: list[tuple[str, dict]] = []
    for doc in documents:
        professor = doc["professor"]
        department = doc["department"]
        dept_short = DEPT_ABBR.get(department, department)

        for i, r in enumerate(doc["reviews"]):
            q = r["quality"]
            d = r["difficulty"]
            prefix = (
                f"{professor} — {dept_short}, {r['course']} "
                f"(Quality {q}/5, Difficulty {d}/5):"
            )
            chunk = f"{prefix} {r['review']}".strip()

            metadata = {
                "professor": professor,
                "department": department,
                "course": r["course"],
                "quality": q if q is not None else -1,
                "difficulty": d if d is not None else -1,
                "grade": r["grade"],
                "source_file": doc["source_file"],
            }
            # Stable id: <ProfessorFile>_<index> (used by ChromaDB in M4).
            chunk_id = f"{Path(doc['source_file']).stem}_{i:04d}"
            metadata["chunk_id"] = chunk_id

            chunks.append((chunk, metadata))
    return chunks


# --- Verification harness -------------------------------------------------


def main() -> None:
    documents = load_documents()
    chunks = chunk_text(documents)

    print(f"Loaded {len(documents)} documents from {DOCUMENTS_DIR}/")
    print(f"Produced {len(chunks)} chunks (one per review)\n")

    print("Per-professor review counts:")
    for doc in documents:
        print(f"  {len(doc['reviews']):>4}  {doc['professor']} ({doc['source_file']})")

    # Verify against the spec: Akshar Varma should have ~117 reviews.
    akshar = next((d for d in documents if "Akshar" in d["professor"]), None)
    if akshar:
        print(f"\nAkshar Varma reviews: {len(akshar['reviews'])} (expected ~117)")

    print("\nSample chunks:")
    for chunk, meta in chunks[:3]:
        print(f"\n  id={meta['chunk_id']}  course={meta['course']}  "
              f"quality={meta['quality']}  grade={meta['grade']}")
        print(f"  text: {chunk[:160]}{'...' if len(chunk) > 160 else ''}")

    # Sanity checks.
    no_prefix = [c for c, _ in chunks if " — " not in c]
    print(f"\nChunks missing professor/course prefix: {len(no_prefix)} (should be 0)")


if __name__ == "__main__":
    main()
