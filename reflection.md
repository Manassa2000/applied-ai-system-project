# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**

- Briefly describe your initial UML design.
- What classes did you include, and what responsibilities did you assign to each?

The UML design consists of 6 classes and 3 enums.

Owner — holds the pet owner's profile and daily time budget (available_minutes, preferred_start_time, preferred_end_time). Responsible for managing the list of pets.
Pet — stores an individual animal's details (species, breed, age, weight, health notes) and owns a list of Task objects. Responsible for task management per pet.
Task — represents a single care activity (walk, feed, meds, etc.). Holds scheduling-relevant data: duration_minutes, priority, frequency, and an optional preferred_time for time-sensitive tasks like medications.
ScheduledTask — a decorator around Task that adds a concrete start_time and end_time. Keeps the original Task data clean while representing placement in the day.
DailyPlan — the output of the scheduler. Holds two lists: tasks that were successfully scheduled and tasks that couldn't fit. Also stores a reasoning log explaining decisions.
Scheduler — the only class with real algorithmic logic. Takes an Owner and produces a DailyPlan by prioritizing tasks, fitting them within available time, assigning time slots, and building a human-readable explanation.
The three enums (TaskType, Priority, Frequency) keep allowed values explicit and prevent invalid inputs like typos in strings.

**b. Design changes**

- Did your design change during implementation?   Yes
- If yes, describe at least one change and why you made it.

One of the biggest changes was in the Task class where the initial design was to make the mark_complete() return boolean. But inorder to handle the implementation of recurring tasks ( daily, twice daily, weekly), it was necessary that it had information about the frequency and due_date(if there was any). Now, the return type changed to either Task/ None. 

Another change was adding get_all_tasks() to Owner. The original UML had Scheduler talking directly to Pet.tasks, but that created an issue that the scheduler would need have to know the internal structure of every pet. Moving the aggregation into Owner means the scheduler only needs to call one method and gets a flat list back, keeping each class's responsibility clean.

Another one was adding four methods : sort_by_time(), filter_tasks(), detect_conflicts(), and mark_task_complete() to the Scheduler which was not initially planned in the designing. This was added only during implementation. 


---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

- What constraints does your scheduler consider (for example: time, priority, preferences)?
- How did you decide which constraints mattered most?

The scheduler considers four constraints: the owner's daily time budget, task priority (HIGH/MEDIUM/LOW, scored 3/2/1), time sensitivity (tasks with a preferred_time like medications get a +1 bonus and are pinned to their exact slot), and the owner's preferred start time (sets where free tasks begin). Time budget was treated as the hardest constraint because it is non-negotiable. Within that, time-sensitive tasks rank above raw priority because a medication at 8 AM cannot be shifted by a scheduling algorithm. Medical necessity has a fixed time dimension that a flat priority score alone does not capture.

**b. Tradeoffs**

- Describe one tradeoff your scheduler makes.
- Why is that tradeoff reasonable for this scenario?

Tradeoff: Greedy scheduling by priority, ignoring total time optimality

The greedy approach is reasonable here because pet care has genuine hard priorities like medications and feeding, and a greedy algorithm naturally honors that by locking them in first.  A busy pet owner needs to trust the plan quickly; "meds were scheduled first because they are HIGH priority" is immediately understandable. The tradeoff is also mitigated by the unscheduled_tasks list, which makes dropped tasks visible so the owner can adjust their time budget or reprioritize manually.

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
- What kinds of prompts or questions were most helpful?

I used AI as a buddy along the whole process from time to time. I felt the kind of prompts that helped the best were inline chat and specifically mentioning a line to ask about what happens there or questions surrounding it. Answers from those prompts were really meaningful and made absolute sense. 

**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
- How did you evaluate or verify what the AI suggested?

In the planning phase when drawing the UML diagram, initially the Claude suggested some design plan which I couldn't understand and didn't think it had some logic. I questioned the Claude again with a scenario asking what will happen in this case and then it changed the design accordingly. 

---

## 4. Testing and Verification

**a. What you tested**

- What behaviors did you test?
- Why were these tests important?

The tests covered six behavioral groups: happy paths (all tasks fit, priority ordering, pinned times), recurrence logic (daily/weekly next-occurrence dates, AS_NEEDED returning None), chronological sorting, conflict detection (overlaps caught, back-to-back not flagged), empty/zero edge cases (no pets, zero budget, exact-fit), and filter correctness. These were important because the scheduler's core promise that HIGH-priority and time-sensitive tasks always get scheduled first within the budget is easy to break silently, and the recurrence and conflict logic involve boundary conditions (off-by-one dates, touching vs. overlapping slots) where a single wrong operator produces incorrect behavior without raising an error.

**b. Confidence**

- How confident are you that your scheduler works correctly?
- What edge cases would you test next if you had more time?

Confident in the core scheduling, priority ordering, recurrence, and conflict detection. All 23 tests pass and cover both happy paths and boundary conditions. Given more time, the next edge cases to test would be two pinned tasks at the same time competing for the same slot, and a TWICE_DAILY task verifying it recurs correctly within the same day rather than the next.

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?

I am mostly satisfied with the backened( implementing scheduling, handling recurring tasks and handling conflicts). 

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?

If I had another iteration, I would first work on the UI improvement. It serves the purpose now but I would really like to add some more colors to the page. 

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?

One important takeaway for me from doing this project was that eventhough AI assists in things and does things quickly, we should always have the upper hand on what needs to be done and how it needs to be done. 
