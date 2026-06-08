"""
generate.py — Milestone 5: Generation and interface.

Ties the pipeline together: takes a user question, retrieves the most relevant
student reviews from ChromaDB (embed.py), and asks a Groq-hosted Llama model to
answer using ONLY those reviews — grounded, cited, and honest about gaps.

Interactive guide:        python generate.py
Run the eval questions:   python generate.py --eval

Requires GROQ_API_KEY in .env (see .env.example).
"""

import os
import sys
from pathlib import Path

from groq import Groq

from embed import retrieve, TOP_K

MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are an Unofficial Guide to Northeastern University \
Computer Science professors. You answer questions using ONLY the student \
reviews provided in the CONTEXT below.

Rules:
- Base your answer solely on the reviews in the CONTEXT. Do not use outside knowledge.
- Cite the professor and course code when you make a claim (e.g. "students in CS3000 said...").
- When reviews disagree, summarize BOTH sides honestly rather than picking one.
- If the CONTEXT does not contain enough information to answer, say so plainly \
("I don't have enough reviews to answer that") instead of guessing.
- Never invent professors, courses, or facts that are not in the CONTEXT.
- Keep answers concise and specific."""


def load_env() -> None:
    """Load .env into os.environ (only keys not already set)."""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def build_context(hits: list[dict]) -> str:
    """Format retrieved chunks into a numbered context block for the prompt."""
    lines = []
    for i, h in enumerate(hits, 1):
        m = h["metadata"]
        lines.append(
            f"[{i}] {m['professor']} — {m['course']} "
            f"(Quality {m['quality']}/5, Difficulty {m['difficulty']}/5, "
            f"Grade {m['grade']}):\n    {h['text'].split(': ', 1)[-1]}"
        )
    return "\n\n".join(lines)


def gather_hits(query: str, k: int, filters) -> list[dict]:
    """Retrieve chunks for a query.

    If `filters` is a list of where-clauses (a comparison question, e.g. two
    professors), retrieve a balanced set for EACH clause and merge them — a
    single top-k retrieval otherwise drowns the less-discussed entity. If
    `filters` is a single dict or None, do one ordinary retrieval.
    """
    if isinstance(filters, list):
        per = max(2, k // len(filters))
        hits: list[dict] = []
        for f in filters:
            hits.extend(retrieve(query, k=per, filters=f))
        return hits
    return retrieve(query, k=k, filters=filters)


def generate_answer(query: str, k: int = TOP_K, filters=None) -> dict:
    """Retrieve relevant reviews and generate a grounded answer with Groq.

    `filters` may be None, a single ChromaDB where-clause, or a LIST of
    where-clauses for balanced per-entity retrieval on comparison questions.
    """
    hits = gather_hits(query, k, filters)
    if not hits:
        return {"answer": "I don't have any reviews matching that question.", "sources": []}

    context = build_context(hits)
    user_message = f"CONTEXT (student reviews):\n\n{context}\n\nQUESTION: {query}"

    client = Groq()  # reads GROQ_API_KEY from environment
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.2,  # low — we want faithful summarization, not creativity
    )
    answer = response.choices[0].message.content.strip()

    sources = [
        {"professor": h["metadata"]["professor"], "course": h["metadata"]["course"]}
        for h in hits
    ]
    return {"answer": answer, "sources": sources}


# --- Interfaces -----------------------------------------------------------


def run_eval() -> None:
    """Run the 5 evaluation questions from the planning doc."""
    questions = [
        ("Who is the better professor for CS1800 — Gregory Aloupis or Lucia Nunez?",
         [{"$and": [{"course": "CS1800"}, {"professor": "Gregory Aloupis"}]},
          {"$and": [{"course": "CS1800"}, {"professor": "Lucia Nunez"}]}]),
        ("What grades do students report getting in Akshar Varma's CS3000?", {"course": "CS3000"}),
        ("How difficult is Akshar Varma's CS3000?", {"course": "CS3000"}),
        ("Is Mark Fontenot's CS3200 worth taking?", {"course": "CS3200"}),
        ("Do students rate Mark Fontenot's CS3200 or CS3500 more highly?",
         [{"course": "CS3200"}, {"course": "CS3500"}]),
    ]
    for q, filters in questions:
        print("=" * 72)
        print(f"Q: {q}\n")
        result = generate_answer(q, filters=filters)
        print(result["answer"])
        print()


def interactive() -> None:
    print("Unofficial Guide to Northeastern CS professors.")
    print("Ask a question (or 'quit' to exit).\n")
    while True:
        try:
            query = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if query.lower() in {"quit", "exit", "q", ""}:
            break
        result = generate_answer(query)
        print(f"\n{result['answer']}\n")
        srcs = ", ".join(f"{s['professor']} ({s['course']})" for s in result["sources"])
        print(f"  sources: {srcs}\n")


def main() -> None:
    load_env()
    if not os.environ.get("GROQ_API_KEY"):
        sys.exit("Missing GROQ_API_KEY in .env (see .env.example).")
    if "--eval" in sys.argv:
        run_eval()
    else:
        interactive()


if __name__ == "__main__":
    main()
