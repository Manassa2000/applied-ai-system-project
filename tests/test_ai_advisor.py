"""
Tests for ai_advisor.py — covers the pure functions (no API calls needed).

All tests run offline; mock mode is used where AI output is required.
"""

from datetime import time

from ai_advisor import (
    _age_category,
    _compute_confidence,
    _dict_to_task,
    _mock_suggest,
    _validate_task_dicts,
    retrieve_guidelines,
)
from pawpal_system import Frequency, Priority, TaskType


# ── _age_category ──────────────────────────────────────────────────────────────

def test_age_category_dog_puppy():
    assert _age_category("dog", 0.5) == "puppy"

def test_age_category_dog_adult():
    assert _age_category("Dog", 3.0) == "adult"

def test_age_category_dog_senior():
    assert _age_category("DOG", 9.0) == "senior"

def test_age_category_cat_kitten():
    assert _age_category("cat", 0.3) == "kitten"

def test_age_category_cat_senior():
    assert _age_category("cat", 11.0) == "senior"

def test_age_category_unknown_species_defaults_to_adult():
    assert _age_category("bird", 5.0) == "adult"

def test_age_category_dog_boundary_8_years_is_senior():
    assert _age_category("dog", 8.0) == "senior"

def test_age_category_dog_just_under_8_is_adult():
    assert _age_category("dog", 7.9) == "adult"


# ── retrieve_guidelines ────────────────────────────────────────────────────────

def test_retrieve_guidelines_returns_dog_docs_for_dog():
    docs = retrieve_guidelines("dog", "Labrador", 3.0, "")
    ids = [d["id"] for d in docs]
    assert any("dog" in id_ for id_ in ids)

def test_retrieve_guidelines_respects_top_k():
    docs = retrieve_guidelines("dog", "Labrador", 3.0, "", top_k=3)
    assert len(docs) <= 3

def test_retrieve_guidelines_species_tag_drives_ranking():
    # Retrieval is tag-based: unknown species ("fish") gets no species bonus,
    # but lifecycle stage ("adult") can still fire.  Dog docs should outscore
    # fish docs for an actual dog query.
    dog_docs  = retrieve_guidelines("dog",  "Labrador", 3.0, "")
    fish_docs = retrieve_guidelines("fish", "",         3.0, "")
    # A real dog query returns more results because the species tag adds +3
    assert len(dog_docs) >= len(fish_docs)

def test_retrieve_guidelines_senior_dog_prioritises_senior_doc():
    docs = retrieve_guidelines("dog", "Labrador", 9.0, "arthritis")
    ids = [d["id"] for d in docs]
    assert "dog_exercise_senior" in ids

def test_retrieve_guidelines_health_notes_surface_relevant_doc():
    # "dental" in health notes should boost dental_care into top results
    docs = retrieve_guidelines("dog", "Labrador", 3.0, "dental disease", top_k=10)
    ids = [d["id"] for d in docs]
    assert "dental_care" in ids


# ── _validate_task_dicts ───────────────────────────────────────────────────────

VALID_TASK = {
    "name": "Morning Walk",
    "task_type": "walk",
    "duration_minutes": 30,
    "priority": "HIGH",
    "frequency": "daily",
}

def test_validate_valid_task_returns_no_errors():
    assert _validate_task_dicts([VALID_TASK]) == []

def test_validate_invalid_task_type():
    errors = _validate_task_dicts([{**VALID_TASK, "task_type": "run"}])
    assert any("task_type" in e for e in errors)

def test_validate_invalid_priority():
    errors = _validate_task_dicts([{**VALID_TASK, "priority": "URGENT"}])
    assert any("priority" in e for e in errors)

def test_validate_invalid_frequency():
    errors = _validate_task_dicts([{**VALID_TASK, "frequency": "hourly"}])
    assert any("frequency" in e for e in errors)

def test_validate_duration_zero_is_invalid():
    errors = _validate_task_dicts([{**VALID_TASK, "duration_minutes": 0}])
    assert any("duration_minutes" in e for e in errors)

def test_validate_duration_181_is_invalid():
    errors = _validate_task_dicts([{**VALID_TASK, "duration_minutes": 181}])
    assert any("duration_minutes" in e for e in errors)

def test_validate_bad_time_format():
    errors = _validate_task_dicts([{**VALID_TASK, "preferred_time": "7am"}])
    assert any("preferred_time" in e for e in errors)

def test_validate_good_time_format_passes():
    assert _validate_task_dicts([{**VALID_TASK, "preferred_time": "07:30"}]) == []

def test_validate_multiple_bad_fields_all_reported():
    bad = {
        "name": "X",
        "task_type": "run",
        "priority": "URGENT",
        "frequency": "hourly",
        "duration_minutes": 0,
    }
    errors = _validate_task_dicts([bad])
    assert len(errors) >= 4


# ── _dict_to_task ──────────────────────────────────────────────────────────────

def test_dict_to_task_basic_fields():
    task = _dict_to_task(VALID_TASK)
    assert task.name == "Morning Walk"
    assert task.task_type == TaskType.WALK
    assert task.priority == Priority.HIGH
    assert task.frequency == Frequency.DAILY
    assert task.duration_minutes == 30

def test_dict_to_task_preferred_time_parsed():
    task = _dict_to_task({**VALID_TASK, "preferred_time": "08:00"})
    assert task.preferred_time == time(8, 0)

def test_dict_to_task_no_preferred_time_is_none():
    task = _dict_to_task(VALID_TASK)
    assert task.preferred_time is None


# ── _mock_suggest ──────────────────────────────────────────────────────────────

def test_mock_suggest_returns_tasks_for_dog():
    retrieved = retrieve_guidelines("dog", "Labrador", 3.0, "")
    result = _mock_suggest("dog", 120, retrieved)
    assert len(result["tasks"]) > 0
    assert result["warnings"] == []

def test_mock_suggest_tasks_fit_within_budget():
    budget = 60
    retrieved = retrieve_guidelines("dog", "Labrador", 3.0, "")
    result = _mock_suggest("dog", budget, retrieved)
    total = sum(t.duration_minutes for t in result["tasks"])
    assert total <= budget

def test_mock_suggest_zero_budget_returns_no_tasks():
    retrieved = retrieve_guidelines("dog", "Labrador", 3.0, "")
    result = _mock_suggest("dog", 0, retrieved)
    assert result["tasks"] == []

def test_mock_suggest_unknown_species_falls_back_gracefully():
    # "fish" has no mock template → falls back to dog tasks
    result = _mock_suggest("fish", 200, [])
    assert len(result["tasks"]) > 0

def test_mock_suggest_result_includes_confidence():
    retrieved = retrieve_guidelines("dog", "Labrador", 3.0, "")
    result = _mock_suggest("dog", 120, retrieved)
    assert "confidence" in result
    assert 0.0 <= result["confidence"] <= 1.0


# ── _compute_confidence ────────────────────────────────────────────────────────

def test_confidence_clean_result_is_high():
    docs = retrieve_guidelines("dog", "Labrador", 3.0, "")
    score = _compute_confidence(docs, warnings=[], iterations=1, total_duration=60, budget=120)
    assert score >= 0.8

def test_confidence_decreases_with_warnings():
    docs = retrieve_guidelines("dog", "Labrador", 3.0, "")
    score_clean = _compute_confidence(docs, warnings=[], iterations=1, total_duration=60, budget=120)
    score_warn  = _compute_confidence(docs, warnings=["w1", "w2"], iterations=1, total_duration=60, budget=120)
    assert score_warn < score_clean

def test_confidence_decreases_with_more_iterations():
    docs = retrieve_guidelines("dog", "Labrador", 3.0, "")
    score_1 = _compute_confidence(docs, warnings=[], iterations=1, total_duration=60, budget=120)
    score_3 = _compute_confidence(docs, warnings=[], iterations=3, total_duration=60, budget=120)
    assert score_3 < score_1

def test_confidence_decreases_with_budget_overrun():
    docs = retrieve_guidelines("dog", "Labrador", 3.0, "")
    score_ok   = _compute_confidence(docs, warnings=[], iterations=1, total_duration=60,  budget=120)
    score_over = _compute_confidence(docs, warnings=[], iterations=1, total_duration=200, budget=120)
    assert score_over < score_ok

def test_confidence_always_between_zero_and_one():
    docs = retrieve_guidelines("dog", "Labrador", 3.0, "")
    cases = [
        ([], 1, 60, 120),
        (["w1", "w2", "w3"], 3, 300, 60),
        ([], 1, 0, 0),
        ([], 0, 0, 0),
    ]
    for warnings, iters, dur, budget in cases:
        score = _compute_confidence(docs, warnings, iters, dur, budget)
        assert 0.0 <= score <= 1.0, f"Out of range for {(warnings, iters, dur, budget)}: {score}"
