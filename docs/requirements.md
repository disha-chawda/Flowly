# FLOWLY | MVP Requirements

## 1. Task Management

FLOWLY shall allow the student to create, edit, delete, and
complete tasks.

### 1.1 Create a Task

The system shall allow the student to create a task by providing
a title. The student may also provide a description, deadline,
estimated time, priority, and category.

### 1.2 Edit a Task

The system shall allow the student to modify the information
associated with an existing task.

### 1.3 Delete a Task

The system shall allow the student to delete an existing task.

### 1.4 Complete a Task

The system shall allow the student to mark a task as completed.

---

## 2. Task Information

Each task shall contain information that helps FLOWLY understand the
student's workload and determine what should be worked on first.

### 2.1 Title

Every task shall have a title.

The title shall clearly describe what the student needs to do.

### 2.2 Description

A task may contain an optional description.

The description can provide additional details about the work that
needs to be completed.

### 2.3 Deadline

A task may have an optional deadline.

When a deadline is provided, FLOWLY shall use it when displaying
upcoming work and generating the daily plan.

### 2.4 Estimated Time

A task may contain an estimated amount of time required to complete it.

The estimated time shall be represented in minutes.

This information shall be used when calculating workload and available
time.

### 2.5 Priority

Each task shall have a priority level:

- High
- Medium
- Low

New tasks shall have Medium priority by default.

Priority shall be used when determining the order of tasks in the
daily plan.

### 2.6 Category

Each task shall have a category.

The available categories for the MVP shall be:

- Academic
- Work
- Personal
- Career

New tasks shall have Personal as the default category.

---

## 3. Commitments

FLOWLY shall allow the student to record fixed time commitments.

A commitment represents a period of time during which the student is
already occupied and cannot normally use that time for tasks.

Examples include:

- Classes
- Work shifts
- Appointments
- Other scheduled obligations

### 3.1 Create a Commitment

The system shall allow the student to create a commitment with a title,
start time, and end time.

### 3.2 Edit a Commitment

The system shall allow the student to modify an existing commitment.

### 3.3 Delete a Commitment

The system shall allow the student to delete an existing commitment.

### 3.4 Commitment Availability

Commitments shall be considered when calculating the student's
available time.

Overlapping commitments shall not cause the same period of time to
be counted more than once.

---

## 4. Dashboard

FLOWLY shall provide a central dashboard that gives the student a
quick overview of their current responsibilities.

The dashboard shall provide the following information:

- Today's tasks
- Upcoming tasks
- Current workload
- Basic daily plan

The dashboard should allow the student to understand what requires
their attention without having to search through multiple screens.

---

## 5. Today's Tasks

FLOWLY shall provide a view of tasks relevant to the current day.

The Today view shall display incomplete tasks that are scheduled for
today or otherwise relevant to the current day's planning.

Completed tasks shall remain distinguishable from incomplete tasks.

---

## 6. Upcoming Tasks

FLOWLY shall provide a view of upcoming incomplete tasks.

Upcoming tasks shall include tasks with future deadlines so that the
student can see work that is approaching before it becomes urgent.

The system shall organize upcoming tasks in a clear and understandable
order.

---

## 7. Workload Summary

FLOWLY shall provide a basic summary of the student's workload.

The workload summary shall compare:

- Estimated time required for incomplete tasks
- Time already occupied by commitments
- Available time

The system shall help the student understand whether their current
workload fits within their available time.

For the MVP, available time shall use a simplified daily planning
window of 16 hours.

This 16-hour window is a temporary MVP assumption and may be replaced
by a more personalized availability model in a future version.

Available time shall never be displayed as a negative value.

---

## 8. Basic Daily Plan

FLOWLY shall generate a basic daily plan using deterministic rules.

The MVP shall not use machine learning or AI to generate the daily plan.

The system shall prioritize incomplete tasks according to the following
order:

1. Earlier deadline
2. Higher priority
3. Earlier creation time

Tasks without a deadline shall not be automatically included in the
daily plan.

The daily plan shall use the estimated time of each task when determining
how much work can fit into the available time.

Fixed commitments shall be considered when determining available time.

---

## 9. Data Persistence

FLOWLY shall persist task and commitment information so that the
student does not lose their information when the application is
closed or restarted.

The system shall store:

- Tasks
- Task attributes
- Task completion state
- Commitments
- Commitment times

The MVP shall use a database for persistent storage.

---

## 10. Simplicity and Modularity

The MVP shall be designed as a simple, modular application.

Task management, commitment management, workload calculations, and
daily planning logic should be separated so that each part can be
developed and tested independently.

The design should allow future functionality to be added without
requiring the existing MVP functionality to be completely rewritten.

Tasks and commitments shall include a source value.

For the MVP, the source shall be `manual`.

This allows future integrations such as Google Calendar, Canvas, email,
and transit services to provide information without changing the
fundamental task and commitment structure.

---

## 11. Usability

FLOWLY shall be simple enough for a student to understand without
extensive instructions.

The interface shall:

- Clearly identify tasks and commitments
- Clearly distinguish completed and incomplete tasks
- Provide understandable labels
- Provide useful validation when required information is missing
- Provide confirmation when appropriate
- Present workload information in an easy-to-understand format

The student should be able to quickly determine what they need to do
and what they should focus on next.

---

## 12. Performance

The MVP shall provide responsive interactions for normal student
workloads.

Common actions such as creating, editing, completing, and deleting
tasks should not require unnecessary processing or noticeable delays.

The application should remain usable with a reasonable number of
tasks and commitments.

---

## 13. Testing

The MVP shall include tests for important business functionality.

Testing shall cover, at minimum:

- Creating tasks
- Editing tasks
- Deleting tasks
- Completing tasks
- Creating and managing commitments
- Workload calculations
- Daily plan prioritization
- Handling tasks with and without deadlines
- Handling overlapping commitments

The purpose of testing is to ensure that the core planning logic
produces consistent and predictable results.

---

# 14. MVP Scope

The FLOWLY MVP shall focus on helping a single student organize
their responsibilities and understand what they should work on.

The MVP includes:

- Manual task management
- Task priorities
- Task categories
- Task deadlines
- Estimated task duration
- Manual commitments
- Today's tasks
- Upcoming tasks
- Workload summary
- Basic daily planning
- Persistent data storage
- Basic testing

The MVP is intentionally limited so that the core product can be
built, tested, and evaluated before more complex functionality is
introduced.

---

# 15. Explicitly Out of Scope for the MVP

The following features are part of the long-term FLOWLY vision but
shall not be implemented in the MVP:

- Google Calendar integration
- Canvas integration
- Gmail or email integration
- Automatic email task extraction
- Transit and transportation integration
- SMS notifications
- Push notifications
- Machine learning-based scheduling
- AI chatbot or assistant
- Automatic task duration prediction
- Advanced personalization
- Advanced analytics
- Internship/application tracking
- Multi-user accounts
- Authentication and authorization
- Automatic synchronization with external services

These features may be introduced in future development stages after
the MVP has been completed and tested.

---

# 16. Future Extensibility

Although the MVP shall remain simple, its structure should allow
FLOWLY to grow into a larger student life management platform.

Future versions may use external integrations and intelligent
planning to answer questions such as:

- What do I need to do today?
- What should I work on first?
- Do I have enough time to finish everything?
- When should I start studying for an upcoming exam?
- When should I leave for class based on transit conditions?
- Did I receive an important academic email?
- What should I prepare for this week?

The MVP should provide a foundation for these future capabilities
without attempting to implement them prematurely.