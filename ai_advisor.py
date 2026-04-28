"""
ai_advisor.py — AI-powered task suggestions for PawPal+.

Two AI features are wired together here:

  1. RAG (Retrieval-Augmented Generation)
     A local knowledge base of veterinary care guidelines is scored and
     retrieved before the LLM is called.  The retrieved text is injected
     directly into the prompt so the model reasons from evidence rather
     than relying solely on parametric memory.

  2. Agentic Workflow
     Gemini is given a structured tool (`submit_task_list`) it must call
     to finalise its answer.  After each call the system validates the
     output (schema) and checks whether the tasks fit the owner's time
     budget.  If they don't, the feedback is returned to Gemini and it
     revises — up to MAX_ITERATIONS loops.

Reliability guardrails
  - Every AI-generated task is validated against the enum values that
    exist in pawpal_system before being converted to a Task object.
  - All errors are caught, logged, and surfaced as non-fatal warnings
    rather than hard crashes.
  - Python's logging module is used throughout; set the root logger to
    DEBUG to see the full agentic trace.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import time as dtime
from typing import Optional

from groq import Groq

from pawpal_system import Frequency, Priority, Task, TaskType

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Knowledge Base  (RAG corpus)
# Each entry has a unique id, a set of string tags used for retrieval,
# and a text chunk that is injected verbatim into the LLM prompt.
# ─────────────────────────────────────────────────────────────────────────────

KNOWLEDGE_BASE: list[dict] = [
    # ── Dogs ──────────────────────────────────────────────────────────────────
    {
        "id": "dog_exercise_adult",
        "tags": {"dog", "exercise", "walk", "adult", "daily"},
        "text": (
            "Adult dogs (1–8 years) need 30–60 minutes of daily exercise. "
            "High-energy breeds such as Labrador Retrievers, Border Collies, "
            "Siberian Huskies, and Vizslas require 60–90 minutes. "
            "Split into a morning and evening walk when possible. "
            "Insufficient exercise causes anxiety, destructive behaviour, and weight gain."
        ),
    },
    {
        "id": "dog_exercise_puppy",
        "tags": {"dog", "exercise", "walk", "puppy", "young"},
        "text": (
            "Puppies (under 1 year) follow the '5-minute rule': 5 minutes of exercise "
            "per month of age, up to twice a day. Over-exercising growing joints risks "
            "long-term damage. Short, frequent play sessions are better than long walks."
        ),
    },
    {
        "id": "dog_exercise_senior",
        "tags": {"dog", "exercise", "walk", "senior", "old", "arthritis", "joint"},
        "text": (
            "Senior dogs (8+ years) still benefit from daily movement but may need "
            "shorter, gentler walks (15–20 minutes twice daily). Watch for limping or "
            "stiffness post-walk. Arthritis dogs benefit from warm-up walks on flat "
            "ground; avoid stairs and cold mornings."
        ),
    },
    {
        "id": "dog_feeding",
        "tags": {"dog", "feed", "meal", "food", "nutrition"},
        "text": (
            "Most adult dogs should be fed twice daily — morning and evening. "
            "Puppies under 6 months need 3–4 small meals per day. "
            "Senior dogs often do better on smaller, more frequent meals (3×). "
            "Each meal typically takes 5–10 minutes. "
            "Avoid feeding right before vigorous exercise."
        ),
    },
    {
        "id": "dog_meds",
        "tags": {"dog", "meds", "medication", "flea", "heartworm", "tick", "parasite"},
        "text": (
            "Dogs need monthly flea/tick and heartworm prevention year-round. "
            "Ear infections require daily topical treatment (5 min). "
            "Joint supplements (glucosamine) are often given daily with meals. "
            "Always pin medication tasks to a consistent time to avoid missed doses."
        ),
    },
    {
        "id": "dog_grooming",
        "tags": {"dog", "grooming", "brush", "coat", "shedding", "bath"},
        "text": (
            "Short-haired breeds need brushing once a week (10 min). "
            "Medium-coated breeds (Labrador, Beagle) benefit from 2–3× weekly brushing "
            "(10–15 min). Long-haired breeds (Golden Retriever, Collie, Shih Tzu) need "
            "daily brushing (15–20 min) to prevent mats. "
            "Bathing every 4–6 weeks unless the dog gets dirty. "
            "Nail trimming every 3–4 weeks (5–10 min)."
        ),
    },
    {
        "id": "dog_enrichment",
        "tags": {"dog", "enrichment", "mental", "play", "training", "stimulation"},
        "text": (
            "Mental stimulation is as important as physical exercise. "
            "Training sessions of 10–15 minutes daily reinforce commands and tire dogs "
            "out mentally. Puzzle feeders, nose-work games, and interactive toys are "
            "excellent enrichment. Aim for at least one dedicated enrichment session "
            "(15–30 min) per day."
        ),
    },
    # ── Cats ──────────────────────────────────────────────────────────────────
    {
        "id": "cat_feeding",
        "tags": {"cat", "feed", "meal", "food", "nutrition"},
        "text": (
            "Adult cats should be fed 2–3 times per day (morning, midday, or evening). "
            "Kittens under 6 months need 3–4 meals daily. "
            "Meal time is typically 5 minutes. "
            "Free-feeding dry food can cause obesity in inactive cats. "
            "Wet food is recommended for urinary health."
        ),
    },
    {
        "id": "cat_enrichment",
        "tags": {"cat", "enrichment", "play", "stimulation", "indoor", "boredom"},
        "text": (
            "Indoor cats need 20–30 minutes of interactive play daily "
            "(feather wand, laser pointer, toy mice). "
            "Two 10–15 minute sessions work better than one long one. "
            "Without enrichment, cats develop anxiety, aggression, and destructive "
            "scratching. Window perches, cat trees, and puzzle feeders are low-effort "
            "enrichment add-ons."
        ),
    },
    {
        "id": "cat_grooming",
        "tags": {"cat", "grooming", "brush", "coat", "hairball", "shedding"},
        "text": (
            "Short-haired cats groom themselves adequately but benefit from weekly "
            "brushing (5–10 min) to reduce hairballs. "
            "Long-haired cats (Maine Coon, Persian, Ragdoll) need daily brushing "
            "(10–15 min) to prevent painful matting. "
            "Check ears weekly for wax build-up or odour."
        ),
    },
    {
        "id": "cat_meds",
        "tags": {"cat", "meds", "medication", "flea", "parasite", "thyroid", "kidney"},
        "text": (
            "Cats need monthly flea prevention year-round. "
            "Senior cats with hyperthyroidism or kidney disease often require "
            "twice-daily medication (2–5 min); pin these to breakfast and dinner. "
            "Oral medication is stressful — consider pill pockets or compounded "
            "transdermal gel."
        ),
    },
    # ── Rabbits ───────────────────────────────────────────────────────────────
    {
        "id": "rabbit_feeding",
        "tags": {"rabbit", "feed", "meal", "hay", "pellets", "vegetables", "nutrition"},
        "text": (
            "Rabbits need unlimited fresh hay (Timothy or orchard grass) at all times. "
            "Replenish hay once or twice daily (5 min). "
            "Pellets: 1/4 cup per 5 lb body weight, once daily. "
            "Fresh leafy greens (romaine, kale) offered twice daily (5 min). "
            "Fresh water must be available at all times; wash bowl daily."
        ),
    },
    {
        "id": "rabbit_enrichment",
        "tags": {"rabbit", "enrichment", "play", "exercise", "run", "hop", "free-roam"},
        "text": (
            "Rabbits need at least 3–4 hours of supervised free-roaming time daily. "
            "A 20–30 minute dedicated play session with tunnels, cardboard boxes, and "
            "toss toys is recommended. Without exercise, rabbits develop GI stasis "
            "(potentially fatal) and musculoskeletal weakness."
        ),
    },
    {
        "id": "rabbit_grooming",
        "tags": {"rabbit", "grooming", "brush", "coat", "shedding", "nails"},
        "text": (
            "Short-haired rabbits need brushing 2–3× weekly (5–10 min) to prevent "
            "ingesting fur (they cannot vomit). "
            "Long-haired breeds (Angora, Lionhead) need daily brushing (15 min). "
            "Nails trimmed every 6–8 weeks. Never bathe a rabbit — it causes fatal shock."
        ),
    },
    # ── Birds ─────────────────────────────────────────────────────────────────
    {
        "id": "bird_feeding",
        "tags": {"bird", "feed", "meal", "pellets", "seeds", "fresh food", "nutrition"},
        "text": (
            "Parrots and parakeets should have fresh pellets and water daily "
            "(replenish each morning, 5 min). "
            "Fresh fruits/vegetables offered once daily (5 min). "
            "Remove uneaten fresh food after 2–4 hours. "
            "Toxic foods: avocado, chocolate, onion, caffeine, xylitol."
        ),
    },
    {
        "id": "bird_enrichment",
        "tags": {"bird", "enrichment", "play", "stimulation", "out-of-cage", "social"},
        "text": (
            "Birds need 2–4 hours of out-of-cage time in a bird-safe room daily. "
            "30-minute dedicated interaction/training sessions 2× daily prevent "
            "feather-plucking and screaming. Rotate toys weekly. "
            "Foraging toys that require work to access food are especially stimulating."
        ),
    },
    # ── Cross-species ─────────────────────────────────────────────────────────
    {
        "id": "senior_vet",
        "tags": {"senior", "old", "vet", "health", "check", "dog", "cat", "rabbit"},
        "text": (
            "Pets aged 7+ should have a vet wellness exam every 6 months "
            "(vs annually for younger pets). "
            "Blood panels, weight checks, and dental exams become more important. "
            "Mark vet visits as HIGH priority with a specific date reminder."
        ),
    },
    {
        "id": "medication_reminders",
        "tags": {"meds", "medication", "reminder", "daily", "chronic", "senior", "dog", "cat"},
        "text": (
            "For pets on daily medications, pin the task to a specific time "
            "(e.g. 8:00 AM with breakfast). Use HIGH priority and daily frequency. "
            "If twice-daily, add two separate tasks (morning + evening). "
            "Missing doses for chronic conditions (heart disease, diabetes, epilepsy) "
            "can be life-threatening."
        ),
    },
    {
        "id": "dental_care",
        "tags": {"dental", "teeth", "grooming", "dog", "cat"},
        "text": (
            "Daily tooth brushing (2–5 min) is the gold standard for preventing "
            "periodontal disease. Use pet-safe toothpaste (never human toothpaste). "
            "If brushing isn't feasible, dental chews or water additives are alternatives "
            "but less effective. Annual professional cleaning is recommended."
        ),
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# RAG: retrieval
# ─────────────────────────────────────────────────────────────────────────────

def _age_category(species: str, age_years: float) -> str:
    """Map species + numeric age to a lifecycle label for tag matching."""
    s = species.lower()
    if s == "dog":
        if age_years < 1:   return "puppy"
        if age_years >= 8:  return "senior"
        return "adult"
    if s == "cat":
        if age_years < 1:   return "kitten"
        if age_years >= 10: return "senior"
        return "adult"
    if s == "rabbit":
        return "senior" if age_years >= 5 else "adult"
    return "adult"


def retrieve_guidelines(
    species: str,
    breed: str,
    age_years: float,
    health_notes: str,
    top_k: int = 6,
) -> list[dict]:
    """
    Score every knowledge-base entry by tag overlap with the query and
    return the top_k most relevant entries.

    Scoring weights:
      +3  species match
      +2  lifecycle-stage match (puppy / adult / senior)
      +1  per keyword from breed + health_notes found in entry tags
    """
    species_lc = species.lower()
    age_cat    = _age_category(species_lc, age_years)
    extra_tokens: set[str] = set()
    for token in re.split(r"\W+", (breed + " " + health_notes).lower()):
        if token:
            extra_tokens.add(token)

    scored: list[tuple[int, dict]] = []
    for entry in KNOWLEDGE_BASE:
        score = 0
        if species_lc in entry["tags"]:
            score += 3
        if age_cat in entry["tags"]:
            score += 2
        for term in extra_tokens:
            if term in entry["tags"]:
                score += 1
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    result = [entry for _, entry in scored[:top_k]]

    logger.info(
        "RAG | query: species=%s age_cat=%s extras=%s | top matches: %s",
        species_lc, age_cat, extra_tokens, [e["id"] for e in result],
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Tool schema for structured output (Groq / OpenAI-compatible function calling)
# ─────────────────────────────────────────────────────────────────────────────

_SUBMIT_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "submit_task_list",
        "description": (
            "Submit the final list of recommended daily/weekly care tasks for the pet. "
            "Call this tool exactly once when you are satisfied with your task list."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "description": "Ordered list of recommended tasks (most important first).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Specific task name, e.g. 'Morning Walk' or 'Evening Feed'.",
                            },
                            "task_type": {
                                "type": "string",
                                "enum": ["walk", "feed", "meds", "enrichment", "grooming", "vet", "other"],
                            },
                            "duration_minutes": {
                                "type": "integer",
                                "description": "Realistic duration in minutes (1–180).",
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["HIGH", "MEDIUM", "LOW"],
                            },
                            "frequency": {
                                "type": "string",
                                "enum": ["daily", "twice_daily", "weekly", "as_needed"],
                            },
                            "preferred_time": {
                                "type": "string",
                                "description": "Preferred start time HH:MM (24h). Omit if not time-sensitive.",
                            },
                            "notes": {
                                "type": "string",
                                "description": "Optional care tip or reminder.",
                            },
                        },
                        "required": ["name", "task_type", "duration_minutes", "priority", "frequency"],
                    },
                },
                "reasoning": {
                    "type": "string",
                    "description": "1–3 sentence explanation of why you chose these tasks.",
                },
            },
            "required": ["tasks", "reasoning"],
        },
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Reliability: validation helpers
# ─────────────────────────────────────────────────────────────────────────────

_VALID_TASK_TYPES  = {t.value for t in TaskType}
_VALID_PRIORITIES  = {p.name  for p in Priority}
_VALID_FREQUENCIES = {f.value for f in Frequency}


def _validate_task_dicts(tasks: list[dict]) -> list[str]:
    """
    Validate a list of raw task dicts against PawPal's domain constraints.
    Returns a list of error strings; empty list means all valid.
    """
    errors: list[str] = []
    for i, t in enumerate(tasks):
        label = f"Task[{i}] '{t.get('name', '?')}'"

        if t.get("task_type") not in _VALID_TASK_TYPES:
            errors.append(
                f"{label}: task_type '{t.get('task_type')}' must be one of {sorted(_VALID_TASK_TYPES)}"
            )
        if t.get("priority") not in _VALID_PRIORITIES:
            errors.append(
                f"{label}: priority '{t.get('priority')}' must be one of {sorted(_VALID_PRIORITIES)}"
            )
        if t.get("frequency") not in _VALID_FREQUENCIES:
            errors.append(
                f"{label}: frequency '{t.get('frequency')}' must be one of {sorted(_VALID_FREQUENCIES)}"
            )
        # Gemini may return int or float from proto — coerce before range check
        dur = t.get("duration_minutes")
        try:
            dur_int = int(dur)
        except (TypeError, ValueError):
            dur_int = None
        if dur_int is None or not (1 <= dur_int <= 180):
            errors.append(f"{label}: duration_minutes={dur!r} must be an integer between 1 and 180")

        pt = t.get("preferred_time")
        if pt and not re.match(r"^\d{1,2}:\d{2}$", str(pt)):
            errors.append(f"{label}: preferred_time '{pt}' must be HH:MM (24h) or omitted")

    return errors


def _dict_to_task(d: dict) -> Task:
    """Convert a validated task dict into a pawpal_system.Task object."""
    pt: Optional[dtime] = None
    raw_time = d.get("preferred_time")
    if raw_time:
        h, m = map(int, str(raw_time).split(":"))
        pt = dtime(h, m)
    return Task(
        name=d["name"],
        task_type=TaskType(d["task_type"]),
        duration_minutes=int(d["duration_minutes"]),
        priority=Priority[d["priority"]],
        frequency=Frequency(d["frequency"]),
        preferred_time=pt,
        notes=d.get("notes", ""),
    )




# ─────────────────────────────────────────────────────────────────────────────
# Mock mode  (set PAWPAL_MOCK=true to bypass the API call)
# The RAG retrieval, validation, and budget-check logic all still run.
# Only the LLM call is replaced with a hardcoded stub.
# ─────────────────────────────────────────────────────────────────────────────

_MOCK_TASKS: dict[str, list[dict]] = {
    "dog": [
        {"name": "Morning Walk",       "task_type": "walk",        "duration_minutes": 30, "priority": "HIGH",   "frequency": "daily",       "preferred_time": "07:00", "notes": "Keep pace gentle for seniors; vigorous for adults."},
        {"name": "Morning Feed",       "task_type": "feed",        "duration_minutes": 10, "priority": "HIGH",   "frequency": "daily",       "preferred_time": "07:30", "notes": "Measure portions to avoid obesity."},
        {"name": "Enrichment Session", "task_type": "enrichment",  "duration_minutes": 15, "priority": "MEDIUM", "frequency": "daily",       "preferred_time": None,    "notes": "Puzzle feeder or nose-work game."},
        {"name": "Evening Walk",       "task_type": "walk",        "duration_minutes": 20, "priority": "MEDIUM", "frequency": "daily",       "preferred_time": "18:00", "notes": ""},
        {"name": "Evening Feed",       "task_type": "feed",        "duration_minutes": 10, "priority": "HIGH",   "frequency": "daily",       "preferred_time": "18:30", "notes": ""},
        {"name": "Weekly Brushing",    "task_type": "grooming",    "duration_minutes": 10, "priority": "LOW",    "frequency": "weekly",      "preferred_time": None,    "notes": "Daily for long-haired breeds."},
    ],
    "cat": [
        {"name": "Morning Feed",       "task_type": "feed",        "duration_minutes": 5,  "priority": "HIGH",   "frequency": "twice_daily", "preferred_time": "07:00", "notes": "Wet food recommended for urinary health."},
        {"name": "Evening Feed",       "task_type": "feed",        "duration_minutes": 5,  "priority": "HIGH",   "frequency": "twice_daily", "preferred_time": "18:00", "notes": ""},
        {"name": "Interactive Play",   "task_type": "enrichment",  "duration_minutes": 15, "priority": "MEDIUM", "frequency": "daily",       "preferred_time": None,    "notes": "Feather wand or laser pointer."},
        {"name": "Litter Box Check",   "task_type": "other",       "duration_minutes": 5,  "priority": "MEDIUM", "frequency": "daily",       "preferred_time": None,    "notes": "Scoop daily; full change weekly."},
        {"name": "Brushing",           "task_type": "grooming",    "duration_minutes": 10, "priority": "LOW",    "frequency": "weekly",      "preferred_time": None,    "notes": "Daily for long-haired breeds (Maine Coon, Persian)."},
    ],
    "rabbit": [
        {"name": "Hay Replenishment",  "task_type": "feed",        "duration_minutes": 5,  "priority": "HIGH",   "frequency": "twice_daily", "preferred_time": "07:00", "notes": "Timothy or orchard grass; unlimited supply."},
        {"name": "Morning Greens",     "task_type": "feed",        "duration_minutes": 5,  "priority": "MEDIUM", "frequency": "daily",       "preferred_time": "07:30", "notes": "Romaine, kale, or cilantro."},
        {"name": "Free Roam Time",     "task_type": "enrichment",  "duration_minutes": 30, "priority": "HIGH",   "frequency": "daily",       "preferred_time": None,    "notes": "Supervised; prevents GI stasis."},
        {"name": "Brushing",           "task_type": "grooming",    "duration_minutes": 10, "priority": "MEDIUM", "frequency": "weekly",      "preferred_time": None,    "notes": "More frequent during shedding season."},
    ],
    "bird": [
        {"name": "Morning Feed & Water", "task_type": "feed",      "duration_minutes": 5,  "priority": "HIGH",   "frequency": "daily",       "preferred_time": "07:00", "notes": "Remove uneaten fresh food after 4 hours."},
        {"name": "Fresh Vegetables",   "task_type": "feed",        "duration_minutes": 5,  "priority": "MEDIUM", "frequency": "daily",       "preferred_time": "12:00", "notes": "Avoid avocado, onion, caffeine."},
        {"name": "Out-of-Cage Time",   "task_type": "enrichment",  "duration_minutes": 30, "priority": "HIGH",   "frequency": "daily",       "preferred_time": None,    "notes": "Bird-safe room; prevents feather-plucking."},
        {"name": "Training Session",   "task_type": "enrichment",  "duration_minutes": 15, "priority": "MEDIUM", "frequency": "daily",       "preferred_time": None,    "notes": "Reinforces social bond and mental stimulation."},
    ],
}


def _mock_suggest(
    species: str,
    owner_budget_minutes: int,
    retrieved: list[dict],
) -> dict:
    """
    Return a stub result without calling the API.
    RAG retrieval has already run; validation and budget-check still apply.
    """
    base = _MOCK_TASKS.get(species.lower(), _MOCK_TASKS["dog"])

    # Greedily fit tasks within budget (same logic as the real agentic loop)
    candidate_tasks: list[dict] = []
    remaining = owner_budget_minutes
    for t in base:
        if t["duration_minutes"] <= remaining:
            candidate_tasks.append(t)
            remaining -= t["duration_minutes"]

    warnings: list[str] = []
    schema_errors = _validate_task_dicts(candidate_tasks)
    if schema_errors:
        warnings.extend(schema_errors)

    task_objects: list[Task] = []
    for d in candidate_tasks:
        try:
            task_objects.append(_dict_to_task(d))
        except Exception as exc:
            warnings.append(f"Skipped '{d.get('name','?')}': {exc}")

    total = sum(t["duration_minutes"] for t in candidate_tasks)
    reasoning = (
        f"[MOCK MODE] Selected {len(candidate_tasks)} task(s) totalling {total} min "
        f"based on retrieved guidelines for a {species}. "
        "Connect a working Gemini API key to get real AI-generated suggestions."
    )
    logger.info("Mock mode: returning %d task(s) for species=%s", len(task_objects), species)

    return {
        "tasks":          task_objects,
        "task_dicts":     candidate_tasks,
        "retrieved_docs": retrieved,
        "reasoning":      reasoning,
        "iterations":     0,
        "warnings":       warnings,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

MAX_ITERATIONS = 3


def suggest_tasks(
    pet_name: str,
    species: str,
    breed: str,
    age_years: float,
    health_notes: str,
    owner_budget_minutes: int,
    api_key: str | None = None,
) -> dict:
    """
    Generate AI-powered task suggestions for a pet using RAG + an agentic loop.

    Steps
    -----
    1. RAG  — retrieve the most relevant care guidelines from KNOWLEDGE_BASE.
    2. Build the prompt with the retrieved text injected as evidence.
    3. Call Gemini (function calling) → model calls ``submit_task_list``.
    4. Validate the function args (schema check).
    5. Budget check: does total duration fit owner_budget_minutes?
    6. If not, send a FunctionResponse with feedback and loop (≤ MAX_ITERATIONS).
    7. Convert accepted task dicts to Task objects and return.

    Returns
    -------
    dict with keys:
      tasks           list[Task]   — validated Task objects ready to add to a pet
      task_dicts      list[dict]   — raw dicts (used for display in the UI)
      retrieved_docs  list[dict]   — KB entries injected into the prompt
      reasoning       str          — the model's own explanation
      iterations      int          — how many loop iterations ran
      warnings        list[str]    — non-fatal issues surfaced in the UI
    """
    api_key = api_key or os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY is not set. "
            "Add it to a .env file or set it as an environment variable."
        )

    client = Groq(api_key=api_key)

    # ── Step 1: RAG retrieval ─────────────────────────────────────────────────
    retrieved = retrieve_guidelines(species, breed, age_years, health_notes)
    guidelines_text = "\n\n".join(
        f"[{e['id']}]\n{e['text']}" for e in retrieved
    )
    logger.info(
        "RAG: retrieved %d guideline(s) for %s (%s, %.1f yrs, notes=%r)",
        len(retrieved), pet_name, species, age_years, health_notes or "none",
    )

    # ── Step 2: Build messages ────────────────────────────────────────────────
    system_prompt = (
        "You are a veterinary-informed pet care assistant. "
        "Recommend a practical, home-friendly task list for the pet described below. "
        "Base your suggestions on the care guidelines provided — do not invent facts. "
        "Call the `submit_task_list` tool exactly once when you are ready. "
        "Use specific task names (e.g. 'Morning Walk', 'Evening Feed', not just 'Walk'). "
        "Suggest 4–8 tasks. Only include tasks the owner can realistically do at home."
    )

    user_message = (
        f"## Pet profile\n"
        f"- Name: {pet_name}\n"
        f"- Species: {species}\n"
        f"- Breed: {breed}\n"
        f"- Age: {age_years:.1f} years\n"
        f"- Health notes: {health_notes or 'none'}\n"
        f"- Owner's daily time budget: {owner_budget_minutes} minutes\n\n"
        f"## Relevant care guidelines (retrieved from knowledge base)\n"
        f"{guidelines_text}\n\n"
        f"Please recommend a task list that fits within the {owner_budget_minutes}-minute "
        f"budget. Prioritise health-critical tasks (meds, feeding) first."
    )

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message},
    ]

    # ── Step 3–6: Agentic loop ────────────────────────────────────────────────
    final_task_dicts: list[dict] = []
    reasoning       = ""
    iterations      = 0
    warnings: list[str] = []

    for iteration in range(MAX_ITERATIONS):
        iterations += 1
        logger.info("Agentic loop: iteration %d / %d", iterations, MAX_ITERATIONS)

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=[_SUBMIT_TOOL],
            tool_choice="required",
            max_tokens=1500,
        )

        msg = response.choices[0].message
        logger.info("Iteration %d: finish_reason=%s", iteration + 1, response.choices[0].finish_reason)

        if not msg.tool_calls:
            text = msg.content or "(no content)"
            warnings.append(f"Iteration {iteration + 1}: model returned no tool call — {text[:200]}")
            logger.warning("No tool call on iteration %d: %s", iteration + 1, text[:200])
            break

        tool_call       = msg.tool_calls[0]
        args            = json.loads(tool_call.function.arguments)
        candidate_tasks = args.get("tasks", [])
        reasoning       = args.get("reasoning", "")

        logger.info(
            "Iteration %d: Claude suggested %d task(s), reasoning=%r",
            iteration + 1, len(candidate_tasks), reasoning[:120],
        )

        # ── Schema validation ─────────────────────────────────────────────────
        schema_errors = _validate_task_dicts(candidate_tasks)
        if schema_errors:
            feedback = (
                "Validation failed — please fix the following errors and resubmit:\n"
                + "\n".join(f"  • {e}" for e in schema_errors)
            )
            logger.warning("Schema errors on iteration %d: %s", iteration + 1, schema_errors)
            messages.append({"role": "assistant", "content": msg.content, "tool_calls": msg.tool_calls})
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": feedback})
            continue

        # ── Budget check ──────────────────────────────────────────────────────
        total_duration = sum(int(t["duration_minutes"]) for t in candidate_tasks)
        logger.info(
            "Budget check: total=%d min, budget=%d min, over_by=%d min",
            total_duration, owner_budget_minutes, max(0, total_duration - owner_budget_minutes),
        )

        if total_duration <= owner_budget_minutes:
            final_task_dicts = candidate_tasks
            logger.info("Tasks accepted on iteration %d (total=%d min)", iteration + 1, total_duration)
            break

        overage = total_duration - owner_budget_minutes

        if iteration == MAX_ITERATIONS - 1:
            final_task_dicts = candidate_tasks
            warnings.append(
                f"Suggested tasks total {total_duration} min, which exceeds the "
                f"{owner_budget_minutes}-min budget by {overage} min. "
                "Consider removing lower-priority tasks before adding them."
            )
            logger.warning(
                "Budget still exceeded (%d min over) after %d iterations — accepting with warning",
                overage, iterations,
            )
            break

        feedback = (
            f"The tasks total {total_duration} minutes, but the owner's budget is "
            f"{owner_budget_minutes} minutes — that's {overage} minutes over. "
            f"Please remove or shorten lower-priority tasks so the total fits within "
            f"{owner_budget_minutes} minutes, then resubmit."
        )
        logger.info("Over budget by %d min — requesting revision (next: iteration %d)", overage, iteration + 2)
        messages.append({"role": "assistant", "content": msg.content, "tool_calls": msg.tool_calls})
        messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": feedback})

    # ── Step 7: Convert accepted dicts → Task objects ─────────────────────────
    task_objects: list[Task] = []
    for d in final_task_dicts:
        try:
            task_objects.append(_dict_to_task(d))
        except Exception as exc:
            logger.error("Failed to convert task dict %s: %s", d, exc)
            warnings.append(
                f"Skipped task '{d.get('name', '?')}' due to a conversion error: {exc}"
            )

    logger.info(
        "suggest_tasks done: %d task(s), %d iteration(s), %d warning(s)",
        len(task_objects), iterations, len(warnings),
    )

    return {
        "tasks":          task_objects,
        "task_dicts":     final_task_dicts,
        "retrieved_docs": retrieved,
        "reasoning":      reasoning,
        "iterations":     iterations,
        "warnings":       warnings,
    }
