# PawPal+ — System Diagram

```mermaid
flowchart TD

    %% ── Tier 1: Human ───────────────────────────────────────────────────────
    Human(["👤 Owner / User"])

    %% ── Tier 2: Streamlit UI ────────────────────────────────────────────────
    subgraph UI["🖥️  Streamlit UI  (app.py)"]
        direction LR
        SetupUI["Setup\nOwner · Pet · Task"]
        AdvisorUI["AI Advisor\nSection 5"]
        ScheduleUI["Schedule View\nSection 4"]
    end

    %% ── Tier 3: Data Model ──────────────────────────────────────────────────
    subgraph Model["📦  Data Model  (pawpal_system.py)"]
        direction LR
        Owner["Owner"] --> Pet["Pet"] --> Task["Task"]
    end

    %% ── Tier 4a: AI Pipeline ────────────────────────────────────────────────
    subgraph AI["🤖  AI Pipeline  (ai_advisor.py)"]
        direction LR

        subgraph RAG["🔍 RAG Retriever"]
            KB[("18 KB\nchunks")] --> Score["Score & rank\n+3 species  +2 lifecycle  +1 keyword"]
            Score --> TopK["Top-6\nguidelines"]
        end

        subgraph Loop["Agentic Loop  ·  max 3 iterations"]
            Prompt["Build Prompt\npet profile + guidelines"] --> LLM["Groq LLM\nllama-3.3-70b"]
            LLM --> Call["submit_task_list\ntool call"]
            Call --> Validate{"Validate\nschema · budget"}
            Validate -->|"❌  errors or over budget\nfeedback → retry"| LLM
            Validate -->|"✅  accepted"| Convert["Convert to\nTask objects"]
        end

        TopK --> Prompt
    end

    %% ── Tier 4b: Scheduler ──────────────────────────────────────────────────
    subgraph Sched["📅  Rule-Based Scheduler  (pawpal_system.py)"]
        direction LR
        Sort["sort_by_time"] --> Plan["generate_plan\ngreedy · priority order"]
        Plan --> Conflicts["detect_conflicts"]
    end

    %% ── Tier 5: Test Suite ──────────────────────────────────────────────────
    subgraph Tests["🧪  Test Suite  (tests/test_pawpal.py · pytest)"]
        direction LR
        T1["Happy path"] 
        T2["Recurrence"]
        T3["Sort & Filter"]
        T4["Conflicts"]
        T5["Edge cases"]
    end

    %% ── Connections ─────────────────────────────────────────────────────────

    Human -->|"enters data"| SetupUI
    Human -->|"requests suggestions"| AdvisorUI
    Human -->|"reviews · approves"| AdvisorUI
    Human -->|"generates"| ScheduleUI

    SetupUI --> Owner

    Pet -->|"species · breed · age\nhealth notes"| Score

    Convert -->|"Task objects\n(after human approval)"| Pet

    Convert --> AdvisorUI
    TopK --> AdvisorUI

    Task --> Sort

    Conflicts --> ScheduleUI
    Plan --> ScheduleUI

    Model -. "pytest" .-> T1 & T2
    Sched -. "pytest" .-> T1 & T3 & T4 & T5

    %% ── Styles ───────────────────────────────────────────────────────────────
    style Human       fill:#dbeafe,stroke:#3b82f6,color:#000
    style UI          fill:#fef9c3,stroke:#ca8a04,color:#000
    style Model       fill:#dcfce7,stroke:#16a34a,color:#000
    style RAG         fill:#f3e8ff,stroke:#9333ea,color:#000
    style Loop        fill:#fee2e2,stroke:#dc2626,color:#000
    style AI          fill:#fdf4ff,stroke:#c026d3,color:#000
    style Sched       fill:#dbeafe,stroke:#2563eb,color:#000
    style Tests       fill:#f1f5f9,stroke:#64748b,color:#000
```

---

## How to read this diagram

The diagram shows data flowing **top → bottom** through five tiers.

### Tier 1 — Human
The owner drives everything. They enter their profile, request AI suggestions, approve those suggestions, and trigger schedule generation.

### Tier 2 — Streamlit UI (`app.py`)
Three logical panels: **Setup** (owner/pet/task forms), **AI Advisor** (Section 5), and **Schedule View** (Section 4). All state is stored in `st.session_state`.

### Tier 3 — Data Model (`pawpal_system.py`)
The core objects: `Owner` holds a list of `Pet`s, each `Pet` holds a list of `Task`s. Every task created — whether manually or by AI — ends up here.

### Tier 4a — AI Pipeline (`ai_advisor.py`)

**RAG Retriever** — Before any LLM call, the pet's species, lifecycle stage, and breed/health keywords are used to score all 18 knowledge-base chunks. The top-6 are injected verbatim into the prompt, so the model reasons from evidence rather than memorised facts.

**Agentic Loop** — The LLM is given a single tool (`submit_task_list`) it *must* call (forced via `tool_choice="required"`). After each call the system runs two automated checks:
- **Schema validation** — are enum values, integer ranges, and time formats correct?
- **Budget check** — does the total duration fit the owner's daily time budget?

If either check fails, a feedback message is appended to the conversation history and the model is asked to revise. This loop runs up to **3 times**. On acceptance, `_dict_to_task()` converts the JSON to real `Task` objects.

### Tier 4b — Rule-Based Scheduler (`pawpal_system.py`)
Purely deterministic. `sort_by_time` orders tasks chronologically (pinned tasks first, unpinned last). `generate_plan` greedily picks tasks high-to-low priority until the time budget is full. `detect_conflicts` scans every pair of scheduled slots for overlaps.

### Tier 5 — Test Suite (`tests/test_pawpal.py`)
22 pytest tests cover the data model and scheduler directly (dotted lines = "verifies"). The AI pipeline is not unit-tested here — its reliability comes from the schema validator and budget checker inside the agentic loop itself.
