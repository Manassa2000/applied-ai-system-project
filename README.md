# PawPal+ — AI-Powered Pet Care Scheduler

A Streamlit app that combines rule-based scheduling with a Retrieval-Augmented Generation (RAG) pipeline and an agentic LLM loop to help pet owners build realistic, personalized daily care plans.

---

## Origin: The Original PawPal+ Project

The original **PawPal+** (Module 2 project) was a fully rule-based Streamlit app. Owners could register pets, add care tasks with priorities and durations, and the system would generate a greedy daily schedule — placing high-priority tasks first, pinning time-sensitive ones (like medications) to their preferred slots, and reporting anything that didn't fit within the owner's time budget. It also handled recurring tasks (daily/weekly auto-recurrence), conflict detection between overlapping slots, and task filtering by pet or status. **It had no AI component at all** — every decision was deterministic Python logic.

This version adds a genuine AI feature on top of that foundation: an AI Advisor that uses a local knowledge base and a Groq-hosted LLM to suggest a personalized task list for any registered pet, grounded in species-specific veterinary guidelines rather than generic heuristics.

---

## What This Project Does and Why It Matters

Pet owners often don't know exactly *how much* exercise a puppy needs, or *how often* a senior cat should see the vet. Generic advice online is hard to turn into a concrete daily plan. PawPal+ closes that gap: given a pet's species, breed, age, and any health notes, the AI Advisor retrieves relevant veterinary guidelines from a local knowledge base, passes them to an LLM, and gets back a structured task list — respecting the owner's actual time budget through a self-correcting feedback loop.

Because AI-generated tasks are converted into the same `Task` objects as manually-entered ones, they immediately flow through the existing priority scheduler, conflict detector, and reasoning log. The AI layer is additive, not a replacement for the rule-based system.

---

## Architecture Overview

> See [`diagram.md`](diagram.md) for the full annotated system diagram.

The system flows through five tiers:

```
👤 Human  →  🖥️ Streamlit UI  →  📦 Data Model  →  ⚙️ Processing  →  📅 Output
```

**Data Model** (`pawpal_system.py`): `Owner` → `Pet` → `Task` hierarchy. All state lives here regardless of how a task was created.

**RAG Retriever** (`ai_advisor.py`): Before any LLM call, 18 veterinary care chunks are scored by tag overlap — species match (+3), lifecycle stage (+2), breed/health keywords (+1). The top-6 are injected directly into the prompt so the model reasons from evidence, not memory.

**Agentic Loop** (`ai_advisor.py`): The LLM is forced (via `tool_choice="required"`) to call a `submit_task_list` tool with a strict JSON schema. After each call the system runs two automated checks — schema validation and budget enforcement — and if either fails, structured feedback is appended to the message history for the model to revise. This repeats up to 3 times.

**Rule-Based Scheduler** (`pawpal_system.py`): Purely deterministic. Greedy priority-first planning, chronological sorting, and pairwise conflict detection. No AI involved.

**Test Suite** (`tests/test_pawpal.py`): 22 pytest tests covering the data model and scheduler. The AI pipeline's reliability comes from the validator and budget checker inside the loop itself.

---

## Setup Instructions

### 1. Clone and create a virtual environment

```bash
git clone <your-repo-url>
cd applied-ai-system-final

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt` installs: `streamlit`, `groq`, `python-dotenv`, `pytest`.

### 3. Get a free Groq API key

1. Go to [console.groq.com](https://console.groq.com) and sign up (free, no credit card).
2. Create an API key under **API Keys**.
3. Create a `.env` file in the project root:

```
GROQ_API_KEY=gsk_your_key_here
```

### 4. Run the app

```bash
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

### 5. Run the tests

```bash
python -m pytest -v
```

---

## Sample Interactions

### Example 1 — Adult Labrador, 120-minute budget

**Input:**
- Pet: Buddy, Dog, Labrador, 3 years, no health notes
- Owner budget: 120 minutes/day

**AI Advisor output (1 iteration):**

| Task | Type | Duration | Priority | Frequency | Time |
|---|---|---|---|---|---|
| Morning Walk | walk | 30 min | HIGH | daily | 07:00 |
| Morning Feed | feed | 10 min | HIGH | daily | 07:30 |
| Evening Feed | feed | 10 min | HIGH | daily | 18:00 |
| Evening Walk | walk | 20 min | MEDIUM | daily | 18:30 |
| Training Session | enrichment | 15 min | MEDIUM | daily | — |
| Weekly Brushing | grooming | 10 min | LOW | weekly | — |

**AI reasoning:** *"Labrador retrievers are high-energy adult dogs requiring 60–90 minutes of daily exercise. I've prioritised two walks and twice-daily feeding, then added an enrichment session for mental stimulation and weekly brushing for coat health, totalling 95 minutes — within the 120-minute budget."*

Retrieved guidelines: `dog_exercise_adult`, `dog_feeding`, `dog_enrichment`, `dog_grooming`

---

### Example 2 — Senior Siamese cat, 60-minute budget

**Input:**
- Pet: Whiskers, Cat, Siamese, 10 years, health notes: "kidney disease"
- Owner budget: 60 minutes/day

**AI Advisor output (1 iteration):**

| Task | Type | Duration | Priority | Frequency | Time |
|---|---|---|---|---|---|
| Morning Feed | feed | 5 min | HIGH | twice_daily | 07:00 |
| Evening Medication | meds | 5 min | HIGH | twice_daily | 18:00 |
| Evening Feed | feed | 5 min | HIGH | twice_daily | 18:30 |
| Interactive Play | enrichment | 15 min | MEDIUM | daily | — |
| Brushing | grooming | 10 min | LOW | weekly | — |

**AI reasoning:** *"Whiskers is a senior cat with kidney disease. Twice-daily feeding and medication are flagged HIGH priority — missed doses for chronic conditions can be life-threatening. Interactive play is included to prevent anxiety in an indoor cat, and weekly brushing keeps shedding manageable. Total: 40 minutes, within the 60-minute budget."*

Retrieved guidelines: `cat_meds`, `cat_feeding`, `senior_vet`, `medication_reminders`, `cat_enrichment`, `cat_grooming`

---

### Example 3 — Budget overage triggers a second iteration

**Input:**
- Pet: Luna, Dog, Husky, 2 years, no health notes
- Owner budget: 45 minutes/day

**Iteration 1:** LLM suggests 7 tasks totalling 110 minutes.

**Feedback sent back to LLM:**
> *"The tasks total 110 minutes, but the owner's budget is 45 minutes — that's 65 minutes over. Please remove or shorten lower-priority tasks so the total fits within 45 minutes, then resubmit."*

**Iteration 2 output (accepted):**

| Task | Type | Duration | Priority | Frequency |
|---|---|---|---|---|
| Morning Walk | walk | 30 min | HIGH | daily |
| Morning Feed | feed | 10 min | HIGH | daily |

**Total: 40 minutes — within budget. Accepted.**

This demonstrates the agentic self-correction: the model doesn't just truncate the list, it reasons about which tasks to drop based on priority.

---

## Design Decisions

### Why Groq + Llama 3.3 instead of a bigger model?

Groq offers a genuine free tier (14,400 requests/day, no billing required) with sub-second latency on `llama-3.3-70b-versatile`. The alternatives explored — Anthropic Claude (requires billing) and Google Gemini (free tier returned `limit: 0` errors on this account) — were not accessible without payment. The chosen stack is reproducible by anyone with a free Groq account.

### Why RAG instead of just prompting the LLM?

A bare prompt asking "what tasks does a Labrador need?" produces inconsistent outputs depending on the model's training data. By grounding the prompt in 18 curated vet-care chunks retrieved by tag overlap, the model produces stable, specific, citation-traceable answers. The retrieved chunks are shown in the UI under an expander, giving full transparency into what the model saw.

### Why `tool_choice="required"` with a strict JSON schema?

Free-form LLM output is unpredictable. Asking the model to "output a JSON list" often produces markdown fences, prose explanations, or wrong field names. Forcing a tool call means the model must conform to a defined schema — enum values, integer ranges, required fields. This makes downstream validation and conversion to `Task` objects reliable, not fragile string parsing.

### Why an agentic loop instead of a single call?

A single call can't enforce the owner's time budget — the model doesn't know it exceeded it until the system checks. The loop lets the system act as a supervisor: check the output, explain the problem in plain language, and give the model a chance to fix it. In practice, budget overages are corrected in one or two extra iterations at negligible cost.

### Trade-offs made

| Decision | Benefit | Cost |
|---|---|---|
| Local knowledge base (18 chunks) | No external API, fast, transparent | Manual to maintain; no real-time vet updates |
| Tag-overlap scoring for RAG | Simple, deterministic, debuggable | Less precise than embedding-based similarity |
| Max 3 agentic iterations | Prevents infinite loops and API cost runaway | Occasionally accepts a slightly over-budget plan with a warning |
| Pure-function AI tests (no mock Groq) | 35 offline tests, no API key needed, never flaky | Live LLM call itself remains untested in CI |
| Streamlit session state | Simplest possible persistence for a demo | State is lost on page refresh; not production-ready |

---

## Testing Summary

**Run:** `python -m pytest -v` — all 58 tests pass across two test files.

### Rule-based scheduler — `tests/test_pawpal.py` (23 tests)

| Group | Count | What is verified |
|---|---|---|
| Happy paths | 3 | Full plan fits budget, priority order respected, pinned time honoured |
| Recurrence | 4 | DAILY +1 day, WEEKLY +7 days, AS_NEEDED returns None, auto-registers on pet |
| Sorting | 2 | Chronological order, unpinned tasks sink to end |
| Conflict detection | 4 | Overlap caught, back-to-back not flagged, same start time caught, clean plan = no warnings |
| Edge cases | 5 | No tasks, no pets, zero budget, exact-fit task, over-budget task |
| Filter edge cases | 3 | No args returns all, unknown pet name, completed=True filter |

### AI advisor — `tests/test_ai_advisor.py` (35 tests, no API key required)

All AI tests run entirely offline against pure functions — no Groq calls are made.

| Group | Count | What is verified |
|---|---|---|
| `_age_category` | 8 | Puppy/adult/senior boundaries for dogs and cats, unknown species default, exact boundary ages |
| `retrieve_guidelines` | 5 | Species-tag drives ranking, `top_k` cap respected, senior/lifecycle prioritisation, health-note boosting |
| `_validate_task_dicts` | 9 | Valid task passes, all four invalid field types caught individually, multi-error reporting |
| `_dict_to_task` | 3 | Field mapping to Task object, `preferred_time` string → `time` object, None when omitted |
| `_mock_suggest` | 5 | Tasks returned for known species, budget enforced, zero-budget returns empty, unknown species falls back gracefully, confidence key present |
| `_compute_confidence` | 5 | Clean result ≥ 0.8, score drops with warnings/extra iterations/budget overrun, always clamped to [0.0, 1.0] |

### Confidence scoring

Every call to `suggest_tasks` and `_mock_suggest` now returns a `confidence` value (0.0–1.0) computed from four signals:

| Signal | Penalty |
|---|---|
| Fewer than 4 RAG docs retrieved | Score scales from 0.5 (0 docs) to 1.0 (4+ docs) |
| Each validation warning | −15% per warning |
| Extra revision iterations | −20% per loop beyond the first |
| Budget overrun | Penalised proportionally to how far over |

A typical successful run (6 docs retrieved, no warnings, 1 iteration, within budget) scores **1.0**. A run that needed 3 iterations and had 2 warnings scores approximately **0.57**.

**What worked well:** Because the AI-specific functions (`_age_category`, `retrieve_guidelines`, `_validate_task_dicts`, `_dict_to_task`) are pure functions with no network dependency, they are straightforward to test exhaustively. The one initially failing test — asserting that an unknown species ("fish") returns an empty list — revealed a genuine insight: the retrieval is tag-based, not species-gated, so lifecycle stage tags like "adult" can surface docs even without a species match. The test was updated to document that behavior rather than paper over it.

**What still isn't tested:** The live LLM call inside `suggest_tasks` (the actual Groq API round-trip) has no automated test. Unit-testing it would require either a mock Groq client (unrealistic responses) or a live key in CI (fragile and costly). The in-loop schema validator and budget checker already enforce correctness at runtime.

**What I learned:** Separating pure logic from I/O makes AI systems testable by design. Every reliability mechanism in the advisor — RAG scoring, validation, budget checking, confidence scoring — is a plain Python function with no side effects, and therefore fully unit-testable without any mocking.

---

## Reflection

### What this project taught me about AI

The biggest lesson was that **AI outputs are not reliable by default — they need structural enforcement**. Using a JSON schema tool call instead of free-form text eliminated an entire class of bugs. The model never produces an invalid `task_type` because it literally cannot — the schema prevents it. This principle (constrain the output space, don't just hope the model behaves) feels like the most transferable thing I learned.

The second lesson was about **RAG as a trust mechanism**. Without it, the model might hallucinate plausible-sounding but wrong advice (e.g., exercise durations for specific breeds). With it, every suggestion is traceable to a specific knowledge-base chunk visible in the UI. That transparency matters — both for debugging and for building the user's trust.

The third lesson was about **the gap between "works in theory" and "works in practice"**. I spent significant time navigating real-world API access issues (Anthropic requires billing, Gemini returned `limit: 0` errors despite a valid key). The final stack — Groq with Llama 3.3 — wasn't the original plan, but finding it forced me to understand the OpenAI-compatible API pattern, which is now the de facto standard across providers.

### What I'd do differently

- **Embedding-based RAG** using sentence transformers would be more accurate than tag overlap for retrieving guidelines, especially for unusual breeds or health conditions.
- **Streaming responses** would improve the UI feel for the agentic loop — right now the spinner blocks until all iterations complete.
- **Persistent storage** (even a local SQLite file) would make the app genuinely useful day-to-day, since Streamlit session state is wiped on refresh.
- **A mock Groq client** would let me test the full `suggest_tasks` agentic loop (multi-iteration feedback, schema-error recovery) without a live API key in CI, completing coverage of the one remaining untested path.
