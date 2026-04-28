import logging
import os

import streamlit as st
from datetime import date, time
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = lambda: None  # python-dotenv not installed; rely on env vars

from pawpal_system import (
    Owner, Pet, Task,
    TaskType, Priority, Frequency,
    Scheduler,
)
from ai_advisor import suggest_tasks

# Load .env if present (for GROQ_API_KEY in local dev)
load_dotenv()

# Route all library loggers to the terminal where `streamlit run` is executed
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
st.title("🐾 PawPal+")

# Priority emoji used in every table throughout the app
PRIORITY_EMOJI = {
    "HIGH":   "🔴 HIGH",
    "MEDIUM": "🟡 MEDIUM",
    "LOW":    "🟢 LOW",
}

# --- Session State Initialization ---
if "owner" not in st.session_state:
    st.session_state.owner = None
# ai_suggestions: dict keyed by pet name → result dict from suggest_tasks()
if "ai_suggestions" not in st.session_state:
    st.session_state.ai_suggestions = {}

# ------------------------------------------------------------------ #
# SECTION 1: Owner Setup
# ------------------------------------------------------------------ #
st.subheader("1. Owner Setup")

owner_name    = st.text_input("Owner name", value="Jordan")
avail_minutes = st.number_input("Available minutes per day", min_value=10, max_value=480, value=120)
start_hour    = st.slider("Day starts at (hour)", 4, 12, 7)

if st.button("Save Owner"):
    st.session_state.owner = Owner(
        name=owner_name,
        available_minutes=int(avail_minutes),
        preferred_start_time=time(start_hour, 0),
        preferred_end_time=time(21, 0),
    )
    st.success(f"Owner '{owner_name}' saved.")

if st.session_state.owner:
    o = st.session_state.owner
    st.caption(f"Current owner: **{o.name}** | Budget: {o.available_minutes} min | Start: {o.preferred_start_time.strftime('%I:%M %p')}")

st.divider()

# ------------------------------------------------------------------ #
# SECTION 2: Add a Pet
# ------------------------------------------------------------------ #
st.subheader("2. Add a Pet")

if st.session_state.owner is None:
    st.info("Save an owner first before adding pets.")
else:
    col1, col2 = st.columns(2)
    with col1:
        pet_name    = st.text_input("Pet name", value="Mochi")
        pet_species = st.selectbox("Species", ["dog", "cat", "rabbit", "bird", "other"])
    with col2:
        pet_breed  = st.text_input("Breed", value="Mixed")
        pet_age    = st.number_input("Age (years)", min_value=0.0, max_value=30.0, value=2.0, step=0.5)
        pet_weight = st.number_input("Weight (kg)", min_value=0.1, max_value=100.0, value=5.0, step=0.5)

    if st.button("Add Pet"):
        new_pet = Pet(
            name=pet_name,
            species=pet_species,
            breed=pet_breed,
            age=pet_age,
            weight=pet_weight,
        )
        st.session_state.owner.add_pet(new_pet)
        st.success(f"Pet '{pet_name}' added to {st.session_state.owner.name}'s profile.")

    if st.session_state.owner.pets:
        st.write("**Pets:**")
        for pet in st.session_state.owner.pets:
            st.caption(f"• {pet.name} ({pet.species}, {pet.age} yrs) — {len(pet.tasks)} task(s)")

st.divider()

# ------------------------------------------------------------------ #
# SECTION 3: Add a Task to a Pet
# ------------------------------------------------------------------ #
st.subheader("3. Add a Task")

if st.session_state.owner is None or not st.session_state.owner.pets:
    st.info("Add at least one pet before adding tasks.")
else:
    pet_names    = [p.name for p in st.session_state.owner.pets]
    selected_pet = st.selectbox("Assign task to", pet_names)

    col1, col2, col3 = st.columns(3)
    with col1:
        task_name = st.text_input("Task name", value="Morning walk")
        task_type = st.selectbox("Type", [t.value for t in TaskType])
    with col2:
        duration  = st.number_input("Duration (min)", min_value=1, max_value=240, value=20)
        priority  = st.selectbox("Priority", ["HIGH", "MEDIUM", "LOW"])
    with col3:
        frequency = st.selectbox("Frequency", [f.value for f in Frequency])
        use_time  = st.checkbox("Pin to a specific time?")
        pref_hour = st.slider("Preferred hour", 0, 23, 8, disabled=not use_time)

    task_notes = st.text_input("Notes (optional)", value="")

    if st.button("Add Task"):
        pet = next(p for p in st.session_state.owner.pets if p.name == selected_pet)
        new_task = Task(
            name=task_name,
            task_type=TaskType(task_type),
            duration_minutes=int(duration),
            priority=Priority[priority],
            frequency=Frequency(frequency),
            preferred_time=time(pref_hour, 0) if use_time else None,
            notes=task_notes,
        )
        pet.add_task(new_task)
        st.success(f"Task '{task_name}' added to {pet.name}.")

    # --- Task table: sorted chronologically via Scheduler.sort_by_time() ---
    all_tasks = st.session_state.owner.get_all_tasks()
    if all_tasks:
        scheduler = Scheduler(st.session_state.owner)
        sorted_tasks = scheduler.sort_by_time(all_tasks)

        st.write("**All tasks** (sorted by preferred time):")
        rows = [
            {
                "Pet":      t.pet.name if t.pet else "?",
                "Task":     t.name,
                "Type":     t.task_type.value,
                "Duration": f"{t.duration_minutes} min",
                "Priority": PRIORITY_EMOJI[t.priority.name],
                "Pinned":   t.preferred_time.strftime("%I:%M %p") if t.preferred_time else "—",
                "Done":     "✓" if t.completed else "—",
            }
            for t in sorted_tasks
        ]
        st.table(rows)

        # --- Filter controls ---
        with st.expander("Filter tasks"):
            filter_col1, filter_col2 = st.columns(2)
            with filter_col1:
                filter_pet  = st.selectbox("By pet", ["All"] + pet_names, key="filter_pet")
            with filter_col2:
                filter_done = st.selectbox("By status", ["All", "Incomplete", "Completed"], key="filter_done")

            completed_arg = None
            if filter_done == "Completed":
                completed_arg = True
            elif filter_done == "Incomplete":
                completed_arg = False

            pet_arg = None if filter_pet == "All" else filter_pet

            # calls Scheduler.filter_tasks() with the chosen filters
            filtered = scheduler.filter_tasks(all_tasks, completed=completed_arg, pet_name=pet_arg)

            if filtered:
                filter_rows = [
                    {
                        "Pet":      t.pet.name if t.pet else "?",
                        "Task":     t.name,
                        "Priority": PRIORITY_EMOJI[t.priority.name],
                        "Duration": f"{t.duration_minutes} min",
                        "Done":     "✓" if t.completed else "—",
                    }
                    for t in filtered
                ]
                st.table(filter_rows)
            else:
                st.info("No tasks match the selected filters.")

st.divider()

# ------------------------------------------------------------------ #
# SECTION 4: Generate Schedule
# ------------------------------------------------------------------ #
st.subheader("4. Generate Today's Schedule")

if st.session_state.owner is None or not st.session_state.owner.get_all_tasks():
    st.info("Add an owner, pets, and tasks before generating a schedule.")
else:
    if st.button("Generate Schedule"):
        scheduler = Scheduler(st.session_state.owner)
        plan      = scheduler.generate_plan(date.today())

        # --- Summary metrics ---
        budget = st.session_state.owner.available_minutes
        used   = plan.get_total_scheduled_time()
        col1, col2, col3 = st.columns(3)
        col1.metric("Budget", f"{budget} min")
        col2.metric("Scheduled", f"{used} min")
        col3.metric("Tasks fit", f"{len(plan.scheduled_tasks)} / {len(plan.scheduled_tasks) + len(plan.unscheduled_tasks)}")

        # --- Scheduled tasks as a table ---
        if plan.scheduled_tasks:
            st.write(f"**Schedule for {plan.date.strftime('%A, %b %d %Y')}:**")
            schedule_rows = [
                {
                    "Time":     f"{st_task.start_time.strftime('%I:%M %p')} → {st_task.end_time.strftime('%I:%M %p')}",
                    "Pet":      st_task.task.pet.name if st_task.task.pet else "?",
                    "Task":     st_task.task.name,
                    "Duration": f"{st_task.task.duration_minutes} min",
                    "Priority": PRIORITY_EMOJI[st_task.task.priority.name],
                    "Pinned":   "📌" if st_task.task.is_time_sensitive() else "—",
                }
                for st_task in plan.scheduled_tasks
            ]
            st.table(schedule_rows)

        # --- Conflict detection via Scheduler.detect_conflicts() ---
        conflicts = scheduler.detect_conflicts(plan.scheduled_tasks)
        if conflicts:
            for warning in conflicts:
                st.warning(f"⚠️ {warning}")
        else:
            st.success("No scheduling conflicts detected.")

        # --- Unscheduled tasks ---
        if plan.unscheduled_tasks:
            st.warning(f"{len(plan.unscheduled_tasks)} task(s) didn't fit in today's budget:")
            skipped_rows = [
                {
                    "Pet":      t.pet.name if t.pet else "?",
                    "Task":     t.name,
                    "Duration": f"{t.duration_minutes} min",
                    "Priority": PRIORITY_EMOJI[t.priority.name],
                }
                for t in plan.unscheduled_tasks
            ]
            st.table(skipped_rows)
        else:
            st.success("All tasks fit within today's budget.")

        # --- Reasoning log ---
        with st.expander("Why this plan?"):
            st.text(plan.get_explanation())

st.divider()

# ------------------------------------------------------------------ #
# SECTION 5: AI Task Advisor
# ------------------------------------------------------------------ #
st.subheader("5. AI Task Advisor")
st.caption(
    "Powered by Llama 3.3 (Groq) + RAG. "
    "The AI retrieves relevant care guidelines from a local knowledge base "
    "and generates a task list that fits your time budget. "
    "Requires GROQ_API_KEY in your environment or a .env file."
)

if st.session_state.owner is None or not st.session_state.owner.pets:
    st.info("Add an owner and at least one pet before using the AI advisor.")
else:
    api_key_present = bool(os.environ.get("GROQ_API_KEY", "").strip())
    if not api_key_present:
        st.warning(
            "GROQ_API_KEY is not set. "
            "Create a `.env` file with `GROQ_API_KEY=sk-...` and restart the app."
        )

    pet_names    = [p.name for p in st.session_state.owner.pets]
    advisor_pet  = st.selectbox("Get suggestions for", pet_names, key="advisor_pet")
    selected_pet = next(p for p in st.session_state.owner.pets if p.name == advisor_pet)

    if st.button("Get AI Suggestions", disabled=not api_key_present):
        with st.spinner(f"Retrieving guidelines and generating tasks for {advisor_pet}…"):
            try:
                result = suggest_tasks(
                    pet_name=selected_pet.name,
                    species=selected_pet.species,
                    breed=selected_pet.breed,
                    age_years=selected_pet.age,
                    health_notes=selected_pet.health_notes,
                    owner_budget_minutes=st.session_state.owner.available_minutes,
                )
                st.session_state.ai_suggestions[advisor_pet] = result
                st.success(
                    f"Generated {len(result['tasks'])} suggestion(s) "
                    f"in {result['iterations']} agentic loop iteration(s)."
                )
            except Exception as exc:
                st.error(f"AI advisor error: {exc}")

    # --- Display last result for the selected pet ---
    result = st.session_state.ai_suggestions.get(advisor_pet)
    if result:
        # Non-fatal warnings (e.g. budget overage after max loops)
        for w in result["warnings"]:
            st.warning(f"⚠️ {w}")

        # Retrieved knowledge base chunks (RAG transparency)
        with st.expander(f"Knowledge base chunks retrieved ({len(result['retrieved_docs'])} docs)"):
            for doc in result["retrieved_docs"]:
                st.markdown(f"**`{doc['id']}`** — {doc['text']}")

        # AI reasoning
        with st.expander("AI reasoning"):
            st.write(result["reasoning"] or "_(no reasoning returned)_")

        # Suggested tasks table
        if result["task_dicts"]:
            total_min = sum(t["duration_minutes"] for t in result["task_dicts"])
            budget    = st.session_state.owner.available_minutes
            st.write(
                f"**Suggested tasks** — {total_min} min total "
                f"({'within' if total_min <= budget else 'over'} {budget}-min budget):"
            )
            suggestion_rows = [
                {
                    "Task":      d["name"],
                    "Type":      d["task_type"],
                    "Duration":  f"{d['duration_minutes']} min",
                    "Priority":  PRIORITY_EMOJI[d["priority"]],
                    "Frequency": d["frequency"],
                    "Pinned":    d.get("preferred_time") or "—",
                    "Notes":     d.get("notes") or "—",
                }
                for d in result["task_dicts"]
            ]
            st.table(suggestion_rows)

            # One-click add button
            if st.button(f"Add all {len(result['tasks'])} suggestions to {advisor_pet}"):
                added = 0
                for task in result["tasks"]:
                    # Skip if a task with the same name already exists on this pet
                    existing_names = {t.name for t in selected_pet.tasks}
                    if task.name not in existing_names:
                        selected_pet.add_task(task)
                        added += 1
                skipped = len(result["tasks"]) - added
                st.success(f"Added {added} task(s) to {advisor_pet}." +
                           (f" Skipped {skipped} duplicate(s)." if skipped else ""))
                # Clear the cached suggestions so stale data isn't re-added
                del st.session_state.ai_suggestions[advisor_pet]
                st.rerun()
        else:
            st.info("No tasks were suggested.")
