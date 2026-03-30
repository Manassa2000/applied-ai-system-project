```mermaid
classDiagram
    class Owner {
        +String name
        +int available_minutes
        +time preferred_start_time
        +time preferred_end_time
        +list~Pet~ pets
        +add_pet(pet: Pet)
        +remove_pet(pet: Pet)
        +get_total_available_time() int
        +get_all_tasks() list~Task~
    }

    class Pet {
        +String name
        +String species
        +String breed
        +float age
        +float weight
        +String health_notes
        +list~Task~ tasks
        +add_task(task: Task)
        +remove_task(task: Task)
        +update_task(task: Task)
        +get_tasks_by_priority() list~Task~
        +get_total_task_duration() int
    }

    class Task {
        +String name
        +TaskType task_type
        +int duration_minutes
        +Priority priority
        +Frequency frequency
        +time preferred_time
        +String notes
        +bool completed
        +date due_date
        +Pet pet
        +mark_complete() Task
        +get_priority_score() int
        +is_time_sensitive() bool
    }

    class ScheduledTask {
        +Task task
        +time start_time
        +time end_time
        +get_duration() int
        +overlaps_with(other: ScheduledTask) bool
    }

    class DailyPlan {
        +date date
        +Owner owner
        +list~ScheduledTask~ scheduled_tasks
        +list~Task~ unscheduled_tasks
        +list~String~ reasoning
        +get_total_scheduled_time() int
        +get_explanation() String
        +is_feasible() bool
    }

    class Scheduler {
        +Owner owner
        +generate_plan(date) DailyPlan
        +sort_by_time(tasks) list~Task~
        +filter_tasks(tasks, completed, pet_name) list~Task~
        +detect_conflicts(scheduled_tasks) list~String~
        +mark_task_complete(task) Task
        +_prioritize_tasks(tasks) list~Task~
        +_fit_tasks(tasks, available_minutes) tuple
        +_assign_times(tasks) list~ScheduledTask~
        +_build_reasoning(scheduled, unscheduled) list~String~
    }

    class TaskType {
        <<enumeration>>
        WALK
        FEED
        MEDS
        ENRICHMENT
        GROOMING
        VET
        OTHER
    }

    class Priority {
        <<enumeration>>
        HIGH
        MEDIUM
        LOW
    }

    class Frequency {
        <<enumeration>>
        DAILY
        TWICE_DAILY
        WEEKLY
        AS_NEEDED
    }

    Owner "1" --> "0..*" Pet : owns
    Pet "1" --> "0..*" Task : has
    Task --> TaskType : typed as
    Task --> Priority : has
    Task --> Frequency : repeats
    Task --> Task : mark_complete() produces
    Scheduler --> Owner : plans for
    Scheduler --> DailyPlan : generates
    DailyPlan "1" --> "0..*" ScheduledTask : scheduled
    DailyPlan "1" --> "0..*" Task : unscheduled
    ScheduledTask --> Task : wraps
```
