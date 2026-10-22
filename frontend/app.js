/*
 * FLOWLY frontend (vanilla JS, no build step).
 *
 * Talks only to the REST API (Design §2, §3 — decoupled frontend):
 *   Tasks:        POST/GET /tasks, GET/PUT/DELETE /tasks/{id}, PATCH /tasks/{id}/completion
 *   Commitments:  POST/GET /commitments, GET/PUT/DELETE /commitments/{id}
 *   Dashboard:    GET /dashboard/today | /upcoming | /workload | /daily-plan  (?date=YYYY-MM-DD)
 *
 * Every API failure uses the error envelope
 *   { "error": { "type", "message", "details": [{ "field", "issue" }] } }
 * and field-level details are rendered next to the matching form input.
 *
 * All user-provided text is rendered with textContent (never innerHTML).
 */
(function () {
  "use strict";

  // ------------------------------------------------------------------
  // Configuration
  // ------------------------------------------------------------------

  /**
   * Resolve the API base URL, in order of precedence:
   *   1. ?api=<url> query parameter
   *   2. <meta name="flowly-api-base" content="..."> (when non-empty)
   *   3. the page's own origin when served over http(s)
   *   4. http://localhost:8000 (e.g. when opened from file://)
   */
  function resolveApiBase() {
    const fromQuery = new URLSearchParams(window.location.search).get("api");
    const meta = document.querySelector('meta[name="flowly-api-base"]');
    const fromMeta = meta ? meta.content.trim() : "";
    let base = fromQuery || fromMeta;
    if (!base) {
      const { protocol, origin } = window.location;
      base = protocol === "http:" || protocol === "https:" ? origin : "http://localhost:8000";
    }
    return base.replace(/\/+$/, "");
  }

  const API_BASE = resolveApiBase();

  const FIELD_LABELS = {
    title: "Title",
    description: "Description",
    deadline: "Deadline",
    estimated_time: "Estimated time",
    priority: "Priority",
    category: "Category",
    completion: "Completion",
    start_time: "Start time",
    end_time: "End time",
    body: "Form",
  };

  // ------------------------------------------------------------------
  // API client
  // ------------------------------------------------------------------

  class ApiError extends Error {
    constructor(status, envelope) {
      super(envelope.message || "Request failed");
      this.status = status;
      this.type = envelope.type || "error";
      this.details = Array.isArray(envelope.details) ? envelope.details : [];
    }
  }

  async function api(path, { method = "GET", body } = {}) {
    const init = { method, headers: { Accept: "application/json" } };
    if (body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }

    let response;
    try {
      response = await fetch(API_BASE + path, init);
    } catch (_networkError) {
      throw new ApiError(0, {
        type: "network_error",
        message: `Could not reach the FLOWLY API at ${API_BASE}. Is the server running?`,
      });
    }

    if (response.status === 204) return null;

    let data = null;
    try {
      data = await response.json();
    } catch (_parseError) {
      data = null;
    }

    if (!response.ok) {
      const envelope =
        data && data.error
          ? data.error
          : { type: "http_error", message: `Request failed (HTTP ${response.status}).` };
      throw new ApiError(response.status, envelope);
    }
    return data;
  }

  const TasksApi = {
    list: () => api("/tasks"),
    create: (payload) => api("/tasks", { method: "POST", body: payload }),
    update: (id, payload) => api(`/tasks/${id}`, { method: "PUT", body: payload }),
    remove: (id) => api(`/tasks/${id}`, { method: "DELETE" }),
    setCompletion: (id, completion) =>
      api(`/tasks/${id}/completion`, { method: "PATCH", body: { completion } }),
  };

  const CommitmentsApi = {
    list: () => api("/commitments"),
    create: (payload) => api("/commitments", { method: "POST", body: payload }),
    update: (id, payload) => api(`/commitments/${id}`, { method: "PUT", body: payload }),
    remove: (id) => api(`/commitments/${id}`, { method: "DELETE" }),
  };

  const DashboardApi = {
    today: (date) => api(`/dashboard/today?date=${encodeURIComponent(date)}`),
    upcoming: (date) => api(`/dashboard/upcoming?date=${encodeURIComponent(date)}`),
    workload: (date) => api(`/dashboard/workload?date=${encodeURIComponent(date)}`),
    dailyPlan: (date) => api(`/dashboard/daily-plan?date=${encodeURIComponent(date)}`),
  };

  // ------------------------------------------------------------------
  // Formatting helpers
  // ------------------------------------------------------------------

  const pad = (n) => String(n).padStart(2, "0");

  function todayISODate() {
    const d = new Date();
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  /**
   * The API stores naive (wall-clock) datetimes, e.g. "2025-02-10T23:59:00".
   * Parse the components directly so the browser does not shift the time.
   */
  function parseWallClock(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/.exec(iso || "");
    if (!m) return null;
    return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0));
  }

  function formatDateTime(iso) {
    const d = parseWallClock(iso);
    return d ? d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : String(iso);
  }

  function formatDate(isoDate) {
    const d = parseWallClock(isoDate);
    return d ? d.toLocaleDateString(undefined, { dateStyle: "full" }) : String(isoDate);
  }

  /** Convert an API datetime to a value for <input type="datetime-local">. */
  function toInputValue(iso) {
    return iso ? String(iso).slice(0, 16) : "";
  }

  function formatMinutes(total) {
    const sign = total < 0 ? "-" : "";
    const abs = Math.abs(total);
    const h = Math.floor(abs / 60);
    const m = abs % 60;
    const parts = [];
    if (h) parts.push(`${h}h`);
    if (m || !h) parts.push(`${m}m`);
    return `${sign}${parts.join(" ")}`;
  }

  function fieldLabel(field) {
    return FIELD_LABELS[field] || field;
  }

  /** Strip Pydantic's "Value error, " prefix for friendlier messages. */
  function cleanIssue(issue) {
    return String(issue || "").replace(/^Value error,\s*/i, "");
  }

  // ------------------------------------------------------------------
  // DOM helpers
  // ------------------------------------------------------------------

  const $ = (sel, root = document) => root.querySelector(sel);

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value === undefined || value === null || value === false) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on") && typeof value === "function") {
        node.addEventListener(key.slice(2), value);
      } else node.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  function setStatus(message, kind = "success") {
    const status = $("#status");
    status.className = `status status--${kind}`;
    status.textContent = message;
  }

  function reportError(error, context) {
    const message = error instanceof ApiError ? error.message : String(error);
    setStatus(`${context}: ${message}`, "error");
  }

  // ------------------------------------------------------------------
  // Form error rendering (error envelope -> field messages)
  // ------------------------------------------------------------------

  function clearFormErrors(form) {
    const summary = $("[data-form-errors]", form);
    summary.hidden = true;
    summary.replaceChildren();
    form.querySelectorAll("[data-error-for]").forEach((p) => {
      p.hidden = true;
      p.textContent = "";
    });
    form.querySelectorAll("[aria-invalid]").forEach((input) => input.removeAttribute("aria-invalid"));
  }

  /**
   * Render an ApiError on a form. Each { field, issue } detail is shown under
   * the matching input; every detail is also listed in the form's summary.
   * `aliases` maps envelope fields to form fields (e.g. model-level "body"
   * errors on a commitment belong to end_time).
   */
  function showFormErrors(form, error, aliases = {}) {
    clearFormErrors(form);
    const summary = $("[data-form-errors]", form);
    const details = error instanceof ApiError ? error.details : [];
    const message = error instanceof ApiError ? error.message : String(error);

    let firstInvalid = null;
    const items = details.map((detail) => {
      const field = aliases[detail.field] || detail.field;
      const issue = cleanIssue(detail.issue);
      const errorEl = form.querySelector(`[data-error-for="${CSS.escape(field)}"]`);
      const input = form.elements.namedItem(field);
      if (errorEl) {
        errorEl.textContent = issue;
        errorEl.hidden = false;
      }
      if (input && input.setAttribute) {
        input.setAttribute("aria-invalid", "true");
        firstInvalid = firstInvalid || input;
      }
      return el("li", { text: `${fieldLabel(field)}: ${issue}` });
    });

    summary.append(el("p", { text: details.length ? "Please fix the following:" : message }));
    if (items.length) summary.append(el("ul", {}, ...items));
    summary.hidden = false;
    if (firstInvalid) firstInvalid.focus();
  }

  // ------------------------------------------------------------------
  // State
  // ------------------------------------------------------------------

  const state = {
    planDate: todayISODate(),
    editingTaskId: null,
    editingCommitmentId: null,
  };

  // ------------------------------------------------------------------
  // Task rendering
  // ------------------------------------------------------------------

  const isComplete = (task) => task.completion === "Complete";

  function renderTaskItem(task, { editable = false } = {}) {
    const complete = isComplete(task);
    const titleId = `task-${task.id}-title-${Math.random().toString(36).slice(2, 8)}`;

    const deadline = task.deadline
      ? el("time", { datetime: task.deadline, text: formatDateTime(task.deadline) })
      : "No deadline";

    const meta = el(
      "dl",
      { class: "meta" },
      el("dt", { text: "Deadline" }), el("dd", {}, deadline),
      el("dt", { text: "Priority" }), el("dd", { class: `priority priority--${task.priority.toLowerCase()}`, text: task.priority }),
      el("dt", { text: "Category" }), el("dd", { text: task.category }),
      el("dt", { text: "Estimate" }), el("dd", { text: task.estimated_time ? `${task.estimated_time} min` : "Not set" }),
      el("dt", { text: "Status" }),
      el("dd", {}, el("span", {
        class: `badge ${complete ? "badge--complete" : "badge--incomplete"}`,
        text: complete ? "✓ Complete" : "○ Incomplete",
      }))
    );

    const toggleLabel = complete ? "Mark incomplete" : "Mark complete";
    const actions = el(
      "div",
      { class: "item-actions" },
      el("button", {
        type: "button",
        class: complete ? "secondary" : "",
        "aria-describedby": titleId,
        text: toggleLabel,
        onclick: () => toggleCompletion(task),
      }),
      editable && el("button", {
        type: "button",
        class: "secondary",
        "aria-describedby": titleId,
        text: "Edit",
        onclick: () => startEditTask(task),
      }),
      editable && el("button", {
        type: "button",
        class: "danger",
        "aria-describedby": titleId,
        text: "Delete",
        onclick: () => deleteTask(task),
      })
    );

    return el(
      "li",
      { class: `task ${complete ? "task--complete" : "task--incomplete"}` },
      el("h4", { class: "task-title", id: titleId, text: task.title }),
      task.description ? el("p", { class: "task-description", text: task.description }) : null,
      meta,
      actions
    );
  }

  function renderTaskList(listEl, tasks, options, emptyText) {
    listEl.replaceChildren(
      ...(tasks.length
        ? tasks.map((task) => renderTaskItem(task, options))
        : [el("li", { class: "empty", text: emptyText })])
    );
  }

  async function loadTasks() {
    const tasks = await TasksApi.list();
    renderTaskList($("#task-list-incomplete"), tasks.filter((t) => !isComplete(t)), { editable: true }, "No incomplete tasks.");
    renderTaskList($("#task-list-complete"), tasks.filter(isComplete), { editable: true }, "No completed tasks.");
  }

  // ------------------------------------------------------------------
  // Task actions
  // ------------------------------------------------------------------

  function readTaskForm(form) {
    const f = form.elements;
    const estimated = f.estimated_time.value.trim();
    return {
      title: f.title.value,
      description: f.description.value,
      deadline: f.deadline.value || null,
      estimated_time: estimated === "" ? null : Number(estimated),
      priority: f.priority.value,
      category: f.category.value,
    };
  }

  function resetTaskForm() {
    const form = $("#task-form");
    form.reset();
    clearFormErrors(form);
    state.editingTaskId = null;
    $("#task-form-heading").textContent = "Add a task";
    $("[data-submit]", form).textContent = "Add task";
    $("[data-cancel]", form).hidden = true;
  }

  function startEditTask(task) {
    const form = $("#task-form");
    clearFormErrors(form);
    state.editingTaskId = task.id;
    const f = form.elements;
    f.title.value = task.title;
    f.description.value = task.description || "";
    f.deadline.value = toInputValue(task.deadline);
    f.estimated_time.value = task.estimated_time ?? "";
    f.priority.value = task.priority;
    f.category.value = task.category;
    $("#task-form-heading").textContent = `Edit task: ${task.title}`;
    $("[data-submit]", form).textContent = "Save changes";
    $("[data-cancel]", form).hidden = false;
    f.title.focus();
  }

  async function submitTaskForm(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = readTaskForm(form);
    const editingId = state.editingTaskId;
    try {
      const saved = editingId === null
        ? await TasksApi.create(payload)
        : await TasksApi.update(editingId, payload);
      resetTaskForm();
      setStatus(editingId === null ? `Added task "${saved.title}".` : `Saved changes to task "${saved.title}".`);
      await refreshAll();
    } catch (error) {
      showFormErrors(form, error);
      if (error instanceof ApiError && error.status === 422) {
        setStatus("The task was not saved. Please fix the highlighted fields.", "error");
      } else {
        reportError(error, "Could not save the task");
      }
    }
  }

  async function toggleCompletion(task) {
    const next = isComplete(task) ? "Incomplete" : "Complete";
    try {
      const saved = await TasksApi.setCompletion(task.id, next);
      setStatus(`Marked task "${saved.title}" as ${next.toLowerCase()}.`);
      await refreshAll();
    } catch (error) {
      reportError(error, "Could not update completion");
    }
  }

  async function deleteTask(task) {
    try {
      await TasksApi.remove(task.id);
      if (state.editingTaskId === task.id) resetTaskForm();
      setStatus(`Deleted task "${task.title}".`);
      await refreshAll();
    } catch (error) {
      reportError(error, "Could not delete the task");
    }
  }

  // ------------------------------------------------------------------
  // Commitments
  // ------------------------------------------------------------------

  function renderCommitmentItem(c) {
    const titleId = `commitment-${c.id}-title`;
    const start = parseWallClock(c.start_time);
    const end = parseWallClock(c.end_time);
    const minutes = start && end ? Math.round((end - start) / 60000) : null;

    return el(
      "li",
      { class: "commitment" },
      el("h4", { id: titleId, text: c.title }),
      el(
        "p",
        { class: "commitment-times" },
        el("time", { datetime: c.start_time, text: formatDateTime(c.start_time) }),
        " to ",
        el("time", { datetime: c.end_time, text: formatDateTime(c.end_time) }),
        minutes !== null ? ` (${formatMinutes(minutes)})` : ""
      ),
      el(
        "div",
        { class: "item-actions" },
        el("button", { type: "button", class: "secondary", "aria-describedby": titleId, text: "Edit", onclick: () => startEditCommitment(c) }),
        el("button", { type: "button", class: "danger", "aria-describedby": titleId, text: "Delete", onclick: () => deleteCommitment(c) })
      )
    );
  }

  async function loadCommitments() {
    const commitments = await CommitmentsApi.list();
    commitments.sort((a, b) => String(a.start_time).localeCompare(String(b.start_time)));
    const list = $("#commitment-list");
    list.replaceChildren(
      ...(commitments.length
        ? commitments.map(renderCommitmentItem)
        : [el("li", { class: "empty", text: "No commitments yet." })])
    );
  }

  function resetCommitmentForm() {
    const form = $("#commitment-form");
    form.reset();
    clearFormErrors(form);
    state.editingCommitmentId = null;
    $("#commitment-form-heading").textContent = "Add a commitment";
    $("[data-submit]", form).textContent = "Add commitment";
    $("[data-cancel]", form).hidden = true;
  }

  function startEditCommitment(c) {
    const form = $("#commitment-form");
    clearFormErrors(form);
    state.editingCommitmentId = c.id;
    const f = form.elements;
    f.title.value = c.title;
    f.start_time.value = toInputValue(c.start_time);
    f.end_time.value = toInputValue(c.end_time);
    $("#commitment-form-heading").textContent = `Edit commitment: ${c.title}`;
    $("[data-submit]", form).textContent = "Save changes";
    $("[data-cancel]", form).hidden = false;
    f.title.focus();
  }

  /**
   * Start/end are required. Missing values are reported in the same envelope
   * shape the API uses, so they render identically to server-side errors.
   * (The update endpoint treats an explicit null time as "set to null", so we
   * never send one.)
   */
  function missingTimeDetails(payload) {
    return ["start_time", "end_time"]
      .filter((field) => !payload[field])
      .map((field) => ({ field, issue: `${fieldLabel(field)} is required` }));
  }

  async function submitCommitmentForm(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const f = form.elements;
    const payload = {
      title: f.title.value,
      start_time: f.start_time.value || null,
      end_time: f.end_time.value || null,
    };
    const aliases = { body: "end_time" };

    const missing = missingTimeDetails(payload);
    if (missing.length) {
      showFormErrors(form, new ApiError(422, { type: "validation_error", message: "Request validation failed", details: missing }), aliases);
      setStatus("The commitment was not saved. Please fix the highlighted fields.", "error");
      return;
    }

    const editingId = state.editingCommitmentId;
    try {
      const saved = editingId === null
        ? await CommitmentsApi.create(payload)
        : await CommitmentsApi.update(editingId, payload);
      resetCommitmentForm();
      setStatus(editingId === null ? `Added commitment "${saved.title}".` : `Saved changes to commitment "${saved.title}".`);
      await refreshAll();
    } catch (error) {
      showFormErrors(form, error, aliases);
      if (error instanceof ApiError && error.status === 422) {
        setStatus("The commitment was not saved. Please fix the highlighted fields.", "error");
      } else {
        reportError(error, "Could not save the commitment");
      }
    }
  }

  async function deleteCommitment(c) {
    try {
      await CommitmentsApi.remove(c.id);
      if (state.editingCommitmentId === c.id) resetCommitmentForm();
      setStatus(`Deleted commitment "${c.title}".`);
      await refreshAll();
    } catch (error) {
      reportError(error, "Could not delete the commitment");
    }
  }

  // ------------------------------------------------------------------
  // Dashboard
  // ------------------------------------------------------------------

  function renderWorkload(w) {
    const container = $("#workload");
    const rows = [
      ["Planning window", w.window_minutes],
      ["Committed time", w.committed_minutes],
      ["Available time", w.available_minutes],
      ["Estimated task time", w.estimated_minutes],
      ["Difference (available minus estimated)", w.difference_minutes],
    ];
    const dl = el(
      "dl",
      { class: "workload" },
      ...rows.flatMap(([label, minutes]) => [
        el("dt", { text: label }),
        el("dd", { text: `${formatMinutes(minutes)} (${minutes} min)` }),
      ])
    );

    const verdict = w.overloaded
      ? el("p", { class: "verdict verdict--over", text: `⚠ Overloaded: estimated work exceeds available time by ${formatMinutes(-w.difference_minutes)}.` })
      : el("p", { class: "verdict verdict--ok", text: `✓ Your work fits: ${formatMinutes(w.difference_minutes)} to spare.` });

    container.replaceChildren(verdict, dl);
  }

  function renderDailyPlan(plan) {
    $("#plan-available").textContent = `Available time: ${formatMinutes(plan.available_minutes)} (${plan.available_minutes} min).`;
    const list = $("#plan-list");
    if (!plan.planned_tasks.length) {
      list.replaceChildren(el("li", { class: "empty", text: "Nothing planned. No incomplete tasks are due on or before this date." }));
      return;
    }
    list.replaceChildren(
      ...plan.planned_tasks.map((t) =>
        el(
          "li",
          { class: `plan-item ${t.fits ? "plan-item--fits" : "plan-item--nofit"}` },
          el("span", { class: "plan-title", text: t.title }),
          el(
            "span",
            { class: "plan-meta" },
            t.deadline ? el("time", { datetime: t.deadline, text: `Due ${formatDateTime(t.deadline)}` }) : "No deadline",
            ` · ${t.priority} priority · `,
            t.estimated_time ? `${t.estimated_time} min` : "No estimate"
          ),
          el("span", {
            class: `badge ${t.fits ? "badge--fits" : "badge--nofit"}`,
            text: t.fits ? "Fits in available time" : "Does not fit",
          })
        )
      )
    );
  }

  async function loadDashboard() {
    const date = state.planDate;
    $("#today-date-label").textContent = formatDate(date);
    const [today, upcoming, workload, plan] = await Promise.all([
      DashboardApi.today(date),
      DashboardApi.upcoming(date),
      DashboardApi.workload(date),
      DashboardApi.dailyPlan(date),
    ]);
    renderTaskList($("#today-list"), today.tasks, { editable: false }, "No tasks due on this date.");
    renderTaskList($("#upcoming-list"), upcoming.tasks, { editable: false }, "No upcoming tasks.");
    renderWorkload(workload);
    renderDailyPlan(plan);
  }

  // ------------------------------------------------------------------
  // Wiring
  // ------------------------------------------------------------------

  async function refreshAll() {
    const results = await Promise.allSettled([loadTasks(), loadCommitments(), loadDashboard()]);
    const failure = results.find((r) => r.status === "rejected");
    if (failure) reportError(failure.reason, "Could not load data");
  }

  function init() {
    $("#api-base").textContent = API_BASE;

    const dateInput = $("#plan-date");
    dateInput.value = state.planDate;
    dateInput.addEventListener("change", () => {
      if (!dateInput.value) return;
      state.planDate = dateInput.value;
      loadDashboard().catch((e) => reportError(e, "Could not load the dashboard"));
    });
    $("#today-btn").addEventListener("click", () => {
      state.planDate = todayISODate();
      dateInput.value = state.planDate;
      loadDashboard().catch((e) => reportError(e, "Could not load the dashboard"));
    });

    const taskForm = $("#task-form");
    taskForm.addEventListener("submit", submitTaskForm);
    $("[data-cancel]", taskForm).addEventListener("click", resetTaskForm);

    const commitmentForm = $("#commitment-form");
    commitmentForm.addEventListener("submit", submitCommitmentForm);
    $("[data-cancel]", commitmentForm).addEventListener("click", resetCommitmentForm);

    refreshAll();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
