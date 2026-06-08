# The Unofficial Guide — Project 1

A Retrieval-Augmented Generation (RAG) system that answers plain-language
questions about Northeastern University Computer Science professors, grounded
in real student reviews from Rate My Professors.

## How to run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then add your Groq API key

python ingest.py              # (optional) inspect ingestion + chunking
python embed.py               # build the ChromaDB index from documents/
python generate.py            # interactive Q&A  (or: python generate.py --eval)
```

Pipeline: [scrape_rmp.py](scrape_rmp.py) collects the corpus →
[ingest.py](ingest.py) loads & chunks → [embed.py](embed.py) embeds + stores →
[generate.py](generate.py) retrieves + generates.

---

## Domain

Course and professor reviews for the Northeastern University Computer Science
department. This knowledge is valuable and hard to find through official
channels because the university's catalog only publishes course *descriptions* —
the formal topics covered. It says nothing about what students actually decide
on: how a specific professor teaches, how harsh the grading is, the real
workload, and which professor to pick for the same course. That experiential
knowledge is crowd-sourced and scattered across review sites. I focus on one
department so the corpus is *dense* — every query has many relevant documents to
draw from, which is what makes retrieval useful.

---

## Document Sources

10 Northeastern CS professors on Rate My Professors. Each professor's full set of
reviews was collected via `scrape_rmp.py` (which queries RMP's GraphQL API) into
one cleaned `.txt` file per professor in [documents/](documents/). **596 reviews
total.**

| # | Source | Type | URL or file path |
|---|--------|------|-----------------|
| 1 | Akshar Varma | RateMyProfessors | https://www.ratemyprofessors.com/professor/3034822 |
| 2 | Kaan Onarlioglu | RateMyProfessors | https://www.ratemyprofessors.com/professor/2338287 |
| 3 | Mark Fontenot | RateMyProfessors | https://www.ratemyprofessors.com/professor/2868024 |
| 4 | Lucia Nunez | RateMyProfessors | https://www.ratemyprofessors.com/professor/2668761 |
| 5 | Justin Wang | RateMyProfessors | https://www.ratemyprofessors.com/professor/2963762 |
| 6 | Karl Lieberherr | RateMyProfessors | https://www.ratemyprofessors.com/professor/430930 |
| 7 | Gregory Aloupis | RateMyProfessors | https://www.ratemyprofessors.com/professor/2903924 |
| 8 | Andrew van der Poel | RateMyProfessors | https://www.ratemyprofessors.com/professor/2574535 |
| 9 | Hongyang Zhang | RateMyProfessors | https://www.ratemyprofessors.com/professor/2689314 |
| 10 | Joydeep Mitra | RateMyProfessors | https://www.ratemyprofessors.com/professor/2948118 |

---

## Chunking Strategy

**Chunk size:** One student review per chunk (variable length, ~50–200 tokens).

**Overlap:** 0 tokens.

**Preprocessing:** Because the corpus was collected via RMP's GraphQL API rather
than HTML scraping, the raw data is already free of navigation, ads, and markup.
`ingest.py` parses each file into a header (professor, department) plus
individual review blocks, and normalizes course codes to uppercase
(`cs1800` → `CS1800`) so metadata filtering is reliable.

**Why these choices fit your documents:** The documents are collections of short,
self-contained student reviews — not flowing prose. So I chunk *per review*
rather than by fixed token count: each chunk is exactly one student's opinion
about one course. A fixed 500-token window would cram ~8–9 unrelated reviews
(different courses, semesters, contradictory sentiments) into one chunk,
producing a blurry "average" embedding that matches everything weakly and
nothing precisely. Overlap is 0 because reviews are independent — there is no
argument flowing across a boundary to preserve. Critically, each chunk is
**prefixed with the professor, department, course, and ratings** so it stays
attributable after being separated from its file (otherwise a chunk like "freest
A of my life, learned nothing" loses all reference to who and what it describes).

**Final chunk count:** 596 chunks across 10 documents.

### Sample chunks (5 labeled, with source)

1. **`Akshar_Varma.txt`** — `Akshar Varma — CS, DS3000 (Quality 5/5, Difficulty 3/5): Professor Varma is great and very understanding, especially for his first time teaching this course. Put in the work and you will succeed. I really liked how even though I didn't go, he offered basically all day office hours the days before the final.`
2. **`Andrew_van_der_Poel.txt`** — `Andrew van der Poel — CS, CS5800 (Quality 5/5, Difficulty 4/5): Drew is absolutely a gem and amazing in Algorithms! He does not assume that students know the pre-requisites and covers every topic right from the foundation and gradually advances the level. Graphs are the best! Assignments are well designed.`
3. **`Kaan_Onarlioglu.txt`** — `Kaan Onarlioglu — CS, CY3740 (Quality 4/5, Difficulty 4/5): it's hard, but i don't have anything bad to say about this class.`
4. **`Lucia_Nunez.txt`** — `Lucia Nunez — CS, CS3500 (Quality 4/5, Difficulty 5/5): She explains concepts clearly and is accessible to students, responding to emails in a timely manner. The grading policies are strict, and some assignment instructions are super vague. This version of the course required a heavy workload.`
5. **`Mark_Fontenot.txt`** — `Mark Fontenot — CS, DS4300 (Quality 2/5, Difficulty 2/5): Fontenot's lectures are filled with tangents, and key concepts are rushed, especially for the final project, which relies on barely taught material. Grading is extremely lenient, with low engagement.`

---

## Embedding Model

**Model used:** `all-MiniLM-L6-v2` via `sentence-transformers`, run locally
(free, 384-dimensional, fast on short English text). Stored in a local ChromaDB
collection using cosine distance. The Groq API key is used only for generation —
Groq has no embeddings endpoint.

**Production tradeoff reflection:** If cost were not a constraint, I would
prioritize **accuracy on domain-specific text** above all else. `all-MiniLM-L6-v2`
is a small, general-purpose model; student reviews use slang, course codes
(CS3000), and implicit sentiment ("freest A of my life" = easy) that a more
capable model embeds more faithfully. I would evaluate a larger general model
such as `all-mpnet-base-v2` or a commercial embedding API (e.g. Voyage, OpenAI
text-embedding-3). The main counterweight is **latency** — larger models embed
and retrieve more slowly, which matters for a real-time query UI, so I would
weigh accuracy gains against response time. **Multilingual support** is not
relevant: the corpus is entirely English. **Context length** is also a non-issue
*because of the per-review chunking* — chunks are ~55 tokens, far below any
model's window; it would only matter if I embedded whole documents. **Local vs.
API:** the local model needs no key and has no rate limits, which is ideal for a
class project; a production deployment serving many users might move embedding to
a hosted API for throughput and to avoid shipping the model to every machine.

---

## Grounded Generation

**LLM:** Groq `llama-3.3-70b-versatile`, temperature 0.2 (low, to favor faithful
summarization over creativity).

**System prompt grounding instruction:** The model is instructed to answer using
**only** the retrieved reviews. The actual system prompt (see
[generate.py](generate.py)):

> You are an Unofficial Guide to Northeastern University Computer Science
> professors. You answer questions using ONLY the student reviews provided in the
> CONTEXT below. Rules: Base your answer solely on the reviews in the CONTEXT. Do
> not use outside knowledge. Cite the professor and course code when you make a
> claim. When reviews disagree, summarize BOTH sides honestly rather than picking
> one. If the CONTEXT does not contain enough information to answer, say so plainly
> ("I don't have enough reviews to answer that") instead of guessing. Never invent
> professors, courses, or facts that are not in the CONTEXT.

**Structural grounding choices:** Retrieved chunks are formatted into a numbered
`CONTEXT` block, each labeled with professor, course, and ratings, before the
question. Because retrieval only returns chunks from the corpus, the model
physically cannot cite anything outside it. This was verified with an out-of-scope
query (see below).

**How source attribution is surfaced:** `generate_answer()` returns a `sources`
list (professor + course for each retrieved chunk) alongside the answer, and the
interactive interface prints it after every response. The model is also
instructed to cite professor/course inline.

---

## Evaluation Report

Run with `python generate.py --eval`.

| # | Question | Expected answer | System response (summarized) | Retrieval quality | Response accuracy |
|---|----------|-----------------|------------------------------|-------------------|-------------------|
| 1 | Better professor for CS1800 — Gregory Aloupis or Lucia Nunez? | Lucia Nunez (3.6/5, 66% would take again) over Aloupis (1.6/5, 18%). | Correctly identifies Lucia Nunez as better, citing her positive reviews and Aloupis's negative ones. (Required a retrieval fix — see Failure Case.) | Relevant (after balanced-retrieval fix) | Accurate |
| 2 | What grades do students report in Akshar Varma's CS3000? | Polarizing — A most common, but notable Fs and Incompletes; many N/A. | Reports A as most common among retrieved reviews, plus "Not sure yet" and N/A. Does **not** surface the Fs/Incompletes. | Relevant | Partially accurate |
| 3 | How difficult is Akshar Varma's CS3000? | Very hard — most rate 5/5, avg ≈ 4.4. | "Majority found it very challenging, most rate difficulty 5/5," with some disagreement. | Relevant | Accurate |
| 4 | Is Mark Fontenot's CS3200 worth taking? | Mixed/polarizing — ~2.8/5, ~49% would take again. | Mixed; quotes both "rude, unhelpful" and "great teacher, super understanding"; concludes it depends. | Relevant | Accurate |
| 5 | Do students rate Fontenot's CS3200 or CS3500 higher? | Roughly equal (~2.8 vs ~2.7); no real difference. | "Difficult to say which is rated more highly — opinions highly divided for both." | Relevant (balanced per-course retrieval) | Accurate |

**Summary:** 4 accurate, 1 partially accurate. Q2 is partially accurate because
top-k=8 retrieval samples only 8 of Akshar Varma's ~117 CS3000 reviews, so the
reported grade distribution under-represents the failing grades that exist in the
full corpus (a sampling limitation, not a generation error).

---

## Failure Case Analysis

**Question that failed:** Q1 — "Who is the better professor for CS1800 — Gregory
Aloupis or Lucia Nunez?" (in the system's *initial* version, before a retrieval
fix).

**What the system returned:** *"I don't have enough reviews to answer that. There
are no reviews for Gregory Aloupis..."* — which is factually wrong: Aloupis has 38
reviews in the corpus.

**Root cause (tied to a specific pipeline stage):** This was a **retrieval**
failure, not a generation failure. With a single top-k=8 semantic search, the
returned chunks were **8 Lucia Nunez reviews and 0 Gregory Aloupis reviews.** Two
factors compounded: (1) Nunez has many more CS1800 reviews, so more of her chunks
sit near *any* CS1800 query; and (2) the phrase "who is *better*" is positively
framed, and Nunez's reviews are positive while Aloupis's are negative — so
Aloupis's reviews were semantically *farther* from the query. Even raising k to 20
surfaced only 1 Aloupis review. The generation step was actually behaving
correctly: its grounding rule made it refuse to invent Aloupis data rather than
hallucinate. The garbage-in came from retrieval. (This validates the
"single top-k is popularity/sentiment-biased" concern.)

**What you would change to fix it (and what I did):** For comparison questions,
do **balanced per-entity retrieval** — one filtered retrieval per professor, then
merge — instead of one global top-k. I added a `gather_hits()` helper in
`generate.py` that accepts a *list* of metadata filters and fetches a balanced
slice for each. After this change, Q1 retrieves both professors' reviews and
correctly concludes Lucia Nunez is the better choice with both sides represented.
This fix was only possible because each chunk stores `professor` and `course` as
filterable metadata.

> **Secondary limitation (Q2):** Even with good retrieval, top-k=8 cannot
> represent the full grade distribution of a 117-review course, so aggregate
> questions ("what grades do people get?") are answered from a sample. A fix
> would be to compute aggregates from metadata directly rather than relying on
> the LLM to count retrieved chunks.

---

## Spec Reflection

<!-- ✍️ WRITE THIS YOURSELF in your own words (2–3 sentences each). It is graded on
     being genuinely yours. Some true material you can draw from:
     - HELPED: the per-review Chunking Strategy you specified made ingestion
       straightforward and kept each chunk attributable; the metadata fields you
       planned enabled the comparison fix.
     - DIVERGED: the spec said top-k=8 single retrieval, but evaluation revealed it
       fails on comparison questions, so you switched to balanced per-entity
       retrieval for those. -->

**One way the spec helped you during implementation:**

**One way your implementation diverged from the spec, and why:**

---

## AI Usage

<!-- ✍️ WRITE THIS YOURSELF. Describe at least 2 specific instances of how you
     DIRECTED the AI and what you reviewed/overrode — it should read as you steering,
     not accepting output. True examples you can write up in your own words:
     - You chose the domain, the 10 professors, and the per-review chunking idea;
       you directed Claude to build scrape_rmp.py after the .json/HTML scraping
       approach failed, and Claude switched to RMP's GraphQL API.
     - You decided to drop Reddit after reviewing its API policy yourself.
     - You ran the evaluation, saw Q1 fail, and directed the balanced-retrieval fix. -->

**Instance 1**

- *What I gave the AI:*
- *What it produced:*
- *What I changed or overrode:*

**Instance 2**

- *What I gave the AI:*
- *What it produced:*
- *What I changed or overrode:*
