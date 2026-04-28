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


