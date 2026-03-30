# PawPal+ (Module 2 Project)

You are building **PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

Your job is to design the system first (UML), then implement the logic in Python, then connect it to the Streamlit UI.

## What you will build

Your final app should:

- Let a user enter basic owner + pet info
- Let a user add/edit tasks (duration + priority at minimum)
- Generate a daily schedule/plan based on constraints and priorities
- Display the plan clearly (and ideally explain the reasoning)
- Include tests for the most important scheduling behaviors

## Getting started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Suggested workflow

1. Read the scenario carefully and identify requirements and edge cases.
2. Draft a UML diagram (classes, attributes, methods, relationships).
3. Convert UML into Python class stubs (no logic yet).
4. Implement scheduling logic in small increments.
5. Add tests to verify key behaviors.
6. Connect your logic to the Streamlit UI in `app.py`.
7. Refine UML so it matches what you actually built.


### Smart Scheduling

PawPal+ uses a priority scheduler to build a daily care plan within the owner's available time budget. Tasks are ranked by priority level (HIGH, MEDIUM, LOW) with a bonus for time-sensitive tasks that have a pinned preferred time, such as medications. Pinned tasks are placed at their exact times first; remaining tasks fill the gaps sequentially. The scheduler also detects time conflicts between any two overlapping slots and returns plain-language warnings without crashing. Recurring tasks (daily or weekly) automatically generate their next occurrence when marked complete, using `timedelta` to calculate the due date. Tasks can be filtered by completion status or pet name, and sorted chronologically, making it easy to query exactly what still needs to happen and when. 

### Testing PawPal+

Command to run tests: python -m pytest

What the test cases cover:

| Group | Tests | What they verify |
|---|---|---|
| **Happy paths** | 3 | Full plan fits, priority order, pinned time respected |
| **Recurrence** | 4 | Daily +1 day, weekly +7 days, AS_NEEDED → None, auto-registers on pet |
| **Sorting** | 2 | Chronological order, unpinned tasks sink to end |
| **Conflict detection** | 4 | Overlap caught, back-to-back not flagged, same start caught, clean plan = no warnings |
| **Empty/zero edge cases** | 5 | No tasks, no pets, zero budget, exact fit, over budget |
| **Filter edge cases** | 3 | No args returns all, unknown pet name, completed=True filter |


Confidence Level : 4.5 Stars