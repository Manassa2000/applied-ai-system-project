from datetime import date, time, timedelta

import pytest

from pawpal_system import (
    Owner, Pet, Task, ScheduledTask,
    TaskType, Priority, Frequency,
    Scheduler,
)


# ------------------------------------------------------------------ #
# Shared helpers
# ------------------------------------------------------------------ #

def make_pet(name="Buddy") -> Pet:
    return Pet(name=name, species="Dog", breed="Labrador", age=3.0, weight=30.0)


def make_task(
    name="Morning Walk",
    duration=30,
    priority=Priority.HIGH,
    frequency=Frequency.DAILY,
    preferred_time=None,
    due_date=None,
) -> Task:
    return Task(
        name=name,
        task_type=TaskType.WALK,
        duration_minutes=duration,
        priority=priority,
        frequency=frequency,
        preferred_time=preferred_time,
        due_date=due_date,
    )


def make_owner(available_minutes=120) -> Owner:
    return Owner(
        name="Alex",
        available_minutes=available_minutes,
        preferred_start_time=time(7, 0),
        preferred_end_time=time(21, 0),
    )


def make_scheduled_task(task, start_h, start_m, end_h, end_m) -> ScheduledTask:
    return ScheduledTask(
        task=task,
        start_time=time(start_h, start_m),
        end_time=time(end_h, end_m),
    )


# ------------------------------------------------------------------ #
# Original tests (kept)
# ------------------------------------------------------------------ #

def test_mark_complete_changes_status():
    task = make_task()
    assert task.completed is False
    task.mark_complete()
    assert task.completed is True


def test_add_task_increases_pet_task_count():
    pet = make_pet()
    assert len(pet.tasks) == 0
    pet.add_task(make_task("Morning Walk"))
    pet.add_task(make_task("Evening Walk"))
    assert len(pet.tasks) == 2


# ------------------------------------------------------------------ #
# Happy paths
# ------------------------------------------------------------------ #

def test_all_tasks_scheduled_when_budget_is_sufficient():
    owner = make_owner(available_minutes=120)
    pet = make_pet()
    pet.add_task(make_task("Walk",  duration=30, priority=Priority.HIGH))
    pet.add_task(make_task("Feed",  duration=10, priority=Priority.MEDIUM))
    pet.add_task(make_task("Groom", duration=15, priority=Priority.LOW))
    owner.add_pet(pet)

    plan = Scheduler(owner).generate_plan(date.today())

    assert len(plan.scheduled_tasks) == 3
    assert len(plan.unscheduled_tasks) == 0
    assert plan.is_feasible() is True


def test_high_priority_scheduled_before_low_priority():
    owner = make_owner(available_minutes=120)
    pet = make_pet()
    # Add LOW first so insertion order cannot mask a sorting bug
    pet.add_task(make_task("Playtime", duration=15, priority=Priority.LOW))
    pet.add_task(make_task("Meds",     duration=10, priority=Priority.HIGH))
    owner.add_pet(pet)

    plan = Scheduler(owner).generate_plan(date.today())
    names = [st.task.name for st in plan.scheduled_tasks]

    assert names.index("Meds") < names.index("Playtime")


def test_pinned_task_starts_at_preferred_time():
    owner = make_owner(available_minutes=120)
    pet = make_pet()
    pet.add_task(make_task("Meds", duration=10, preferred_time=time(8, 0)))
    owner.add_pet(pet)

    plan = Scheduler(owner).generate_plan(date.today())
    meds_slot = next(st for st in plan.scheduled_tasks if st.task.name == "Meds")

    assert meds_slot.start_time == time(8, 0)


# ------------------------------------------------------------------ #
# Recurrence logic
# ------------------------------------------------------------------ #

def test_daily_task_recurs_next_day():
    today = date.today()
    task = make_task(frequency=Frequency.DAILY, due_date=today)
    next_task = task.mark_complete()

    assert next_task is not None
    assert next_task.due_date == today + timedelta(days=1)
    assert next_task.completed is False


def test_weekly_task_recurs_in_seven_days():
    today = date.today()
    task = make_task(frequency=Frequency.WEEKLY, due_date=today)
    next_task = task.mark_complete()

    assert next_task is not None
    assert next_task.due_date == today + timedelta(days=7)


def test_as_needed_task_returns_none_on_complete():
    task = make_task(frequency=Frequency.AS_NEEDED)
    next_task = task.mark_complete()

    assert next_task is None


def test_mark_task_complete_registers_next_on_pet():
    owner = make_owner()
    pet = make_pet()
    task = make_task(frequency=Frequency.DAILY, due_date=date.today())
    pet.add_task(task)
    owner.add_pet(pet)

    scheduler = Scheduler(owner)
    scheduler.mark_task_complete(task)

    # Pet should now have the original + the new recurrence
    assert len(pet.tasks) == 2
    assert pet.tasks[-1].completed is False


# ------------------------------------------------------------------ #
# Sorting correctness
# ------------------------------------------------------------------ #

def test_sort_by_time_returns_chronological_order():
    owner = make_owner()
    pet = make_pet()
    # Add intentionally out of order
    pet.add_task(make_task("Evening Walk", preferred_time=time(18, 0)))
    pet.add_task(make_task("Meds",         preferred_time=time(8, 0)))
    pet.add_task(make_task("Breakfast",    preferred_time=time(7, 30)))
    owner.add_pet(pet)

    scheduler = Scheduler(owner)
    sorted_tasks = scheduler.sort_by_time(owner.get_all_tasks())
    times = [t.preferred_time for t in sorted_tasks]

    assert times == sorted(times)


def test_sort_by_time_unpinned_tasks_go_to_end():
    owner = make_owner()
    pet = make_pet()
    pet.add_task(make_task("Free Task",  preferred_time=None))
    pet.add_task(make_task("Early Task", preferred_time=time(7, 0)))
    owner.add_pet(pet)

    scheduler = Scheduler(owner)
    sorted_tasks = scheduler.sort_by_time(owner.get_all_tasks())

    assert sorted_tasks[0].name == "Early Task"
    assert sorted_tasks[-1].name == "Free Task"


# ------------------------------------------------------------------ #
# Conflict detection
# ------------------------------------------------------------------ #

def test_detect_conflicts_flags_overlapping_tasks():
    owner = make_owner()
    scheduler = Scheduler(owner)
    task_a = make_task("Walk")
    task_b = make_task("Feed")

    slots = [
        make_scheduled_task(task_a, 7, 0,  7, 30),   # 07:00–07:30
        make_scheduled_task(task_b, 7, 15, 7, 45),   # 07:15–07:45 — overlaps
    ]
    warnings = scheduler.detect_conflicts(slots)

    assert len(warnings) == 1
    assert "Walk" in warnings[0]
    assert "Feed" in warnings[0]


def test_detect_conflicts_back_to_back_is_not_a_conflict():
    owner = make_owner()
    scheduler = Scheduler(owner)
    task_a = make_task("Walk")
    task_b = make_task("Feed")

    slots = [
        make_scheduled_task(task_a, 7, 0,  7, 30),   # ends at 07:30
        make_scheduled_task(task_b, 7, 30, 7, 45),   # starts at 07:30 — no overlap
    ]
    warnings = scheduler.detect_conflicts(slots)

    assert len(warnings) == 0


def test_detect_conflicts_same_start_time_is_a_conflict():
    owner = make_owner()
    scheduler = Scheduler(owner)
    task_a = make_task("Walk")
    task_b = make_task("Feed")

    slots = [
        make_scheduled_task(task_a, 8, 0, 8, 30),
        make_scheduled_task(task_b, 8, 0, 8, 10),   # same start
    ]
    warnings = scheduler.detect_conflicts(slots)

    assert len(warnings) == 1


def test_detect_conflicts_clean_plan_returns_no_warnings():
    owner = make_owner(available_minutes=120)
    pet = make_pet()
    pet.add_task(make_task("Walk",  duration=30, preferred_time=time(7, 0)))
    pet.add_task(make_task("Feed",  duration=10, preferred_time=time(8, 0)))
    owner.add_pet(pet)

    plan = Scheduler(owner).generate_plan(date.today())
    warnings = Scheduler(owner).detect_conflicts(plan.scheduled_tasks)

    assert warnings == []


# ------------------------------------------------------------------ #
# Edge cases — empty / zero states
# ------------------------------------------------------------------ #

def test_pet_with_no_tasks_has_zero_duration():
    pet = make_pet()
    assert pet.get_total_task_duration() == 0


def test_owner_with_no_pets_generates_empty_plan():
    owner = make_owner()
    plan = Scheduler(owner).generate_plan(date.today())

    assert plan.scheduled_tasks == []
    assert plan.unscheduled_tasks == []
    assert plan.is_feasible() is True


def test_zero_budget_skips_all_tasks():
    owner = make_owner(available_minutes=0)
    pet = make_pet()
    pet.add_task(make_task("Walk", duration=30))
    owner.add_pet(pet)

    plan = Scheduler(owner).generate_plan(date.today())

    assert len(plan.scheduled_tasks) == 0
    assert len(plan.unscheduled_tasks) == 1


def test_task_fitting_exactly_into_budget_is_included():
    owner = make_owner(available_minutes=30)
    pet = make_pet()
    pet.add_task(make_task("Walk", duration=30))   # exactly 30 min — must fit
    owner.add_pet(pet)

    plan = Scheduler(owner).generate_plan(date.today())

    assert len(plan.scheduled_tasks) == 1
    assert len(plan.unscheduled_tasks) == 0


def test_task_exceeding_budget_is_unscheduled():
    owner = make_owner(available_minutes=20)
    pet = make_pet()
    pet.add_task(make_task("Walk", duration=30))   # 30 > 20 — must be dropped
    owner.add_pet(pet)

    plan = Scheduler(owner).generate_plan(date.today())

    assert len(plan.scheduled_tasks) == 0
    assert len(plan.unscheduled_tasks) == 1


# ------------------------------------------------------------------ #
# Edge cases — filters
# ------------------------------------------------------------------ #

def test_filter_tasks_no_args_returns_all():
    owner = make_owner()
    pet = make_pet()
    pet.add_task(make_task("Walk"))
    pet.add_task(make_task("Feed"))
    owner.add_pet(pet)

    result = Scheduler(owner).filter_tasks(owner.get_all_tasks())
    assert len(result) == 2


def test_filter_tasks_unknown_pet_returns_empty():
    owner = make_owner()
    pet = make_pet("Buddy")
    pet.add_task(make_task("Walk"))
    owner.add_pet(pet)

    result = Scheduler(owner).filter_tasks(owner.get_all_tasks(), pet_name="Ghost")
    assert result == []


def test_filter_tasks_completed_true_excludes_incomplete():
    owner = make_owner()
    pet = make_pet()
    done_task = make_task("Meds")
    done_task.mark_complete()
    pet.add_task(done_task)
    pet.add_task(make_task("Walk"))   # incomplete
    owner.add_pet(pet)

    result = Scheduler(owner).filter_tasks(owner.get_all_tasks(), completed=True)
    assert len(result) == 1
    assert result[0].name == "Meds"
