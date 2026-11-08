import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import EscalationRules from "@/components/EscalationRules";
import IntakeTaskTemplate from "@/components/IntakeTaskTemplate";
import RequirementTasks from "@/components/RequirementTasks";

// pob-027 (DEC-SCOPE-434 I3, I6, I7, I10): the Team Lead's task template and escalation rules, and the tasks on a requirement.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const TEMPLATE = { task_template: [{ kind: "sourcing", title: "Prepare the sourcing plan", due_in_hours: 24 }] };
const TASK = { id: "K1", kind: "sourcing", title: "Prepare the sourcing plan", due_at: "2030-01-10T05:00:00Z", status: "open", completed_at: null,
  assignee: { id: "U1", full_name: "Priya Recruiter" }, can_complete: true };
const RULE = { id: "R1", event_type: "follow_up_overdue", after_hours: 4, notify: "reporting_manager", active: true, created_at: "2030-01-01T00:00:00Z" };

let sent: { url: string; method: string; body: Record<string, unknown> | null }[];
let reply: (url: string, method: string) => Response;

beforeEach(() => {
  sent = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    sent.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
    return Promise.resolve(reply(url, method));
  }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("IntakeTaskTemplate", () => {
  it("loads, adds a task, saves the whole template and confirms", async () => {
    reply = (_url, method) => (method === "PUT" ? res({ task_template: [...TEMPLATE.task_template, { kind: "screening", title: "Call the shortlist", due_in_hours: 12 }] }) : res(TEMPLATE));
    render(<IntakeTaskTemplate />);
    expect(await screen.findByDisplayValue("Prepare the sourcing plan")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Add task" }));
    fireEvent.change(screen.getByLabelText("Task 2 type"), { target: { value: "screening" } });
    fireEvent.change(screen.getByLabelText("Task 2 title"), { target: { value: "Call the shortlist" } });
    fireEvent.change(screen.getByLabelText("Task 2 due after (hours)"), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Save tasks" }));
    expect(await screen.findByText("Task template saved.")).toBeTruthy();
    expect(sent.find((s) => s.method === "PUT")!.body).toEqual({ task_template: [{ kind: "sourcing", title: "Prepare the sourcing plan", due_in_hours: 24 },
      { kind: "screening", title: "Call the shortlist", due_in_hours: 12 }] });
  });

  it("refuses a blank title and out-of-range hours before sending", async () => {
    reply = () => res(TEMPLATE);
    render(<IntakeTaskTemplate />);
    const title = await screen.findByLabelText("Task 1 title");
    fireEvent.change(title, { target: { value: " " } });
    fireEvent.change(screen.getByLabelText("Task 1 due after (hours)"), { target: { value: "721" } });
    fireEvent.click(screen.getByRole("button", { name: "Save tasks" }));
    expect(await screen.findByText("Enter a title")).toBeTruthy();
    expect(screen.getByText("Enter whole hours from 1 to 720")).toBeTruthy();
    expect(sent.some((s) => s.method === "PUT")).toBe(false);
  });

  it("removes a task and shows the empty state", async () => {
    reply = () => res(TEMPLATE);
    render(<IntakeTaskTemplate />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove task 1" }));
    expect(screen.getByText("No tasks: a new owner starts with none.")).toBeTruthy();
  });

  it("hides the per-task legend visually (QA-01): the field labels already name the task", async () => {
    reply = () => res(TEMPLATE);
    const { container } = render(<IntakeTaskTemplate />);
    await screen.findByLabelText("Task 1 title");
    expect(container.querySelector("legend")!.className).toBe("visually-hidden");
  });

  it("says when the template cannot be loaded", async () => {
    reply = () => res({ detail: "boom" }, 500);
    render(<IntakeTaskTemplate />);
    expect(await screen.findByText("The task template could not be loaded. Refresh the page to try again.")).toBeTruthy();
  });
});

describe("EscalationRules", () => {
  it("lists the rules, adds one and switches one off", async () => {
    const added = { ...RULE, id: "R2", event_type: "requirement_unowned", after_hours: 8, notify: "all_team_leads" };
    reply = (url, method) => (method === "POST" ? res({ rule: added }, 201) : method === "PATCH" ? res({ rule: { ...RULE, active: false } }) : res({ items: [RULE] }));
    render(<EscalationRules />);
    const row = await screen.findByRole("row", { name: /Follow-up overdue/ });
    expect(within(row).getByText("The owner's Team Lead")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("When"), { target: { value: "requirement_unowned" } });
    fireEvent.change(screen.getByLabelText("After (hours)"), { target: { value: "8" } });
    fireEvent.change(screen.getByLabelText("Tell"), { target: { value: "all_team_leads" } });
    fireEvent.click(screen.getByRole("button", { name: "Add rule" }));
    expect(await screen.findByRole("row", { name: /Requirement without an owner/ })).toBeTruthy();
    expect(sent.find((s) => s.method === "POST")!.body).toEqual({ event_type: "requirement_unowned", after_hours: 8, notify: "all_team_leads" });
    fireEvent.click(within(row).getByRole("button", { name: "Switch off" }));
    await waitFor(() => expect(sent.find((s) => s.method === "PATCH")!.body).toEqual({ active: false }));
    expect(await within(screen.getByRole("row", { name: /Follow-up overdue/ })).findByRole("button", { name: "Switch on" })).toBeTruthy();
  });

  it("shows the empty state", async () => {
    reply = () => res({ items: [] });
    render(<EscalationRules />);
    expect(await screen.findByText("No escalation rules yet.")).toBeTruthy();
  });

  it("explains that a requirement without an owner goes to every Team Lead (QA-03)", async () => {
    reply = () => res({ items: [RULE] });
    const { container } = render(<EscalationRules />);
    expect(await screen.findByText("hours after it was received; with no owner, every Team Lead is told")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("When"), { target: { value: "follow_up_overdue" } });
    expect(screen.getByText("hours past its due time")).toBeTruthy();
    expect(container.querySelector("th span")!.className).toBe("visually-hidden");
  });
});

describe("RequirementTasks", () => {
  it("lists the tasks and marks one done", async () => {
    reply = (_url, method) => (method === "POST" ? res({ task: { ...TASK, status: "done", completed_at: "2030-01-09T00:00:00Z", can_complete: false } }) : res({ items: [TASK] }));
    render(<RequirementTasks requirementId="J1" version="v1" />);
    expect(await screen.findByText("Prepare the sourcing plan")).toBeTruthy();
    expect(screen.getByText(/Priya Recruiter/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Mark done: Prepare the sourcing plan" }));
    expect(await screen.findByText("Done")).toBeTruthy();
    expect(sent.find((s) => s.method === "POST")!.url).toBe("/api/v1/recruiter/requirements/J1/tasks/K1/complete");
    expect(screen.queryByRole("button", { name: /Mark done/ })).toBeNull();
  });

  it("shows the empty and error states", async () => {
    reply = () => res({ items: [] });
    render(<RequirementTasks requirementId="J1" version="v1" />);
    expect(await screen.findByText("No tasks on this requirement.")).toBeTruthy();
    cleanup();
    reply = () => res({ detail: "boom" }, 500);
    render(<RequirementTasks requirementId="J1" version="v1" />);
    expect((await screen.findByRole("alert")).textContent).toBe("Tasks could not be loaded. Refresh the page to try again."); // QA-02
  });

  it("shows the server's refusal when completing fails", async () => {
    reply = (_url, method) => (method === "POST" ? res({ detail: "This task is already closed" }, 409) : res({ items: [TASK] }));
    render(<RequirementTasks requirementId="J1" version="v1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Mark done: Prepare the sourcing plan" }));
    expect(await screen.findByText("This task is already closed")).toBeTruthy();
  });
});
