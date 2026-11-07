import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RequirementChecklist from "@/components/RequirementChecklist";
import { detailMessage } from "@/lib/apiErrors";
import { reasonLabel } from "@/lib/recruiterFollowUps";
import { actionLabel } from "@/lib/recruiterHistory";
import type { Checklist } from "@/lib/requirementChecklist";

// pob-016 (DEC-SCOPE-419): the validation checklist card. The server decides every rule; these check what is shown, what is sent and how a failure reads.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const URL = "/api/v1/recruiter/requirements/R1/checklist";

const checklist = (over: Partial<Checklist> = {}): Checklist => ({
  items: [
    { key: "openings", label: "Number of openings", hint: "How many people.", status: null, follow_up: null },
    { key: "salary_budget", label: "Salary budget", hint: "A range.", status: "missing", follow_up: { id: "F1", status: "open", due_at: "2026-11-09T05:00:00Z", contact: "Dev Decider" } },
    { key: "timeline", label: "Joining date and turnaround", hint: "When.", status: "confirmed", follow_up: null },
  ],
  summary: { total: 3, confirmed: 1, not_applicable: 0, missing: 1, not_reviewed: 1, complete: false },
  blocking: { on: false, company_rule: null, global_rule: false },
  override: null, sourcing_started: false, warning: null, company_id: "CO1",
  can_edit: true, can_override: false, can_set_company_rule: false, can_set_global_rule: false,
  ...over,
});

let calls: { url: string; method: string; body: unknown }[];
let answer: (url: string, method: string) => Response;

beforeEach(() => {
  calls = [];
  answer = () => res(checklist());
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    return answer(url, method);
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const show = async (onSaved = vi.fn()) => {
  render(<RequirementChecklist requirementId="R1" status="requirement_received" onSaved={onSaved} />);
  await screen.findByRole("group", { name: "Salary budget" });
  return onSaved;
};
const group = (name: string) => within(screen.getByRole("group", { name }));

describe("the checklist card", () => {
  it("shows a loading state, then each item with its answer and the summary", async () => {
    render(<RequirementChecklist requirementId="R1" status="requirement_received" onSaved={vi.fn()} />);
    expect(screen.getByText("Loading the checklist…")).toBeTruthy();
    await screen.findByRole("group", { name: "Salary budget" });
    expect(screen.getByText("1 of 3 settled")).toBeTruthy();
    expect((group("Salary budget").getByRole("radio", { name: "Missing" }) as HTMLInputElement).checked).toBe(true);
    expect((group("Joining date and turnaround").getByRole("radio", { name: "Confirmed" }) as HTMLInputElement).checked).toBe(true);
    expect(group("Number of openings").getAllByRole("radio").some((r) => (r as HTMLInputElement).checked)).toBe(false);
    expect(group("Number of openings").getByText("Not reviewed")).toBeTruthy();
  });

  it("shows who a missing item's follow-up is with", async () => {
    await show();
    expect(group("Salary budget").getByText(/Follow-up with Dev Decider due/)).toBeTruthy();
  });

  it("says when a missing item's follow-up was closed by hand", async () => {
    const closed = checklist();
    closed.items[1].follow_up!.status = "done";
    answer = () => res(closed);
    await show();
    expect(group("Salary budget").getByText("Its follow-up is closed.")).toBeTruthy();
  });

  it("offers a retry when the load fails", async () => {
    answer = () => res({ detail: "Job requirement not found" }, 404);
    render(<RequirementChecklist requirementId="R1" status="requirement_received" onSaved={vi.fn()} />);
    expect((await screen.findByRole("alert")).textContent).toBe("Job requirement not found");
    answer = () => res(checklist());
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByRole("group", { name: "Salary budget" });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("re-reads when the requirement's status changes", async () => {
    const { rerender } = render(<RequirementChecklist requirementId="R1" status="requirement_received" onSaved={vi.fn()} />);
    await screen.findByRole("group", { name: "Salary budget" });
    answer = () => res(checklist({ sourcing_started: true, warning: "Sourcing has already started, so this does not stop it." }));
    rerender(<RequirementChecklist requirementId="R1" status="sourcing" onSaved={vi.fn()} />);
    expect(await screen.findByText(/already started/)).toBeTruthy();
  });

  it("saves an answer, tells the screen and reports it", async () => {
    const onSaved = await show();
    answer = () => res(checklist({ items: checklist().items.map((i) => (i.key === "openings" ? { ...i, status: "confirmed" as const } : i)) }));
    fireEvent.click(group("Number of openings").getByRole("radio", { name: "Confirmed" }));
    await screen.findByText("Number of openings: Confirmed.");
    expect(calls.at(-1)).toEqual({ url: `${URL}/items/openings`, method: "PUT", body: { status: "confirmed" } });
    expect(onSaved).toHaveBeenCalledOnce();
  });

  it("says a follow-up was added when an item is marked missing", async () => {
    await show();
    answer = () => res(checklist({ items: checklist().items.map((i) => (i.key === "openings" ? { ...i, status: "missing" as const, follow_up: { id: "F2", status: "open" as const, due_at: "2026-11-09T05:00:00Z", contact: null } } : i)) }));
    fireEvent.click(group("Number of openings").getByRole("radio", { name: "Missing" }));
    await screen.findByText("Number of openings: Missing. A follow-up was added.");
    expect(group("Number of openings").getByText(/Follow-up with the client due/)).toBeTruthy();
  });

  it("keeps the saved answer and shows the server's refusal when a save fails", async () => {
    await show();
    answer = () => res({ detail: "This company already has 50 open follow-ups" }, 409);
    fireEvent.click(group("Number of openings").getByRole("radio", { name: "Missing" }));
    expect((await screen.findByRole("alert")).textContent).toBe("This company already has 50 open follow-ups");
    expect((group("Number of openings").getByRole("radio", { name: "Missing" }) as HTMLInputElement).checked).toBe(false);
  });

  it("sends one save at a time", async () => {
    await show();
    let finish: (r: Response) => void = () => {};
    answer = () => new Promise<Response>((resolve) => { finish = resolve; }) as unknown as Response;
    fireEvent.click(group("Number of openings").getByRole("radio", { name: "Confirmed" }));
    fireEvent.click(group("Number of openings").getByRole("radio", { name: "Missing" }));
    expect(calls.filter((c) => c.method === "PUT")).toHaveLength(1);
    finish(res(checklist()));
    await screen.findByText(/Number of openings: Confirmed/);
  });

  it("shows answers as text with no radios to someone who cannot edit", async () => {
    answer = () => res(checklist({ can_edit: false }));
    render(<RequirementChecklist requirementId="R1" status="requirement_received" onSaved={vi.fn()} />);
    await screen.findByRole("group", { name: "Salary budget" });
    expect(screen.queryAllByRole("radio")).toHaveLength(0);
    expect(group("Salary budget").getByText("Missing")).toBeTruthy();
  });

  it("shows the warning after sourcing has started", async () => {
    answer = () => res(checklist({ sourcing_started: true, warning: "Sourcing has already started, so this does not stop it." }));
    await show();
    expect(screen.getByText(/already started/)).toBeTruthy();
  });
});

describe("blocking and the override", () => {
  it("says sourcing is blocked and shows no override form to the owner", async () => {
    answer = () => res(checklist({ blocking: { on: true, company_rule: true, global_rule: false } }));
    await show();
    expect(screen.getByText("Sourcing cannot start until this is complete.")).toBeTruthy();
    expect(screen.queryByLabelText("Reason for the override")).toBeNull();
  });

  it("says nothing is blocked when the rule is off", async () => {
    await show();
    expect(screen.getByText("This checklist does not block sourcing.")).toBeTruthy();
  });

  it("asks a Team Lead for a reason before overriding", async () => {
    answer = () => res(checklist({ blocking: { on: true, company_rule: true, global_rule: false }, can_override: true, can_edit: false }));
    await show();
    fireEvent.click(screen.getByRole("button", { name: "Override the checklist" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Give a reason for the override.");
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);
  });

  it("sends the override and shows who did it", async () => {
    answer = () => res(checklist({ blocking: { on: true, company_rule: true, global_rule: false }, can_override: true, can_edit: false }));
    const onSaved = await show();
    answer = () => res(checklist({ blocking: { on: true, company_rule: true, global_rule: false }, can_edit: false,
      override: { reason: "Client on leave", by: { id: "M1", full_name: "Mira Manager", active: true }, at: "2026-11-07T05:00:00Z" } }));
    fireEvent.change(screen.getByLabelText("Reason for the override"), { target: { value: " Client on leave " } });
    fireEvent.click(screen.getByRole("button", { name: "Override the checklist" }));
    await screen.findByText("Checklist overridden.");
    expect(calls.at(-1)).toEqual({ url: `${URL}/override`, method: "POST", body: { reason: "Client on leave" } });
    expect(screen.getByText(/Overridden by Mira Manager/)).toBeTruthy();
    expect(screen.getByText(/Client on leave/)).toBeTruthy();
    expect(screen.queryByLabelText("Reason for the override")).toBeNull();
    expect(onSaved).toHaveBeenCalledOnce();
  });
});

describe("the rules", () => {
  it("hides the rules from those who cannot change them", async () => {
    await show();
    expect(screen.queryByLabelText("Rule for this company")).toBeNull();
    expect(screen.queryByLabelText("Rule for every other company")).toBeNull();
  });

  it("saves a company rule, null meaning the global rule, and re-reads", async () => {
    answer = () => res(checklist({ can_set_company_rule: true, blocking: { on: true, company_rule: true, global_rule: false } }));
    await show();
    const select = screen.getByLabelText("Rule for this company") as HTMLSelectElement;
    expect(select.value).toBe("block");
    answer = (_url, method) => (method === "PUT" ? res({ block_sourcing: null }) : res(checklist({ can_set_company_rule: true })));
    fireEvent.change(select, { target: { value: "global" } });
    await screen.findByText("This company's rule is saved.");
    const put = calls.find((c) => c.method === "PUT");
    expect(put).toEqual({ url: "/api/v1/recruiter/companies/CO1/checklist-rule", method: "PUT", body: { block_sourcing: null } });
    await waitFor(() => expect((screen.getByLabelText("Rule for this company") as HTMLSelectElement).value).toBe("global"));
    expect(calls.at(-1)?.method).toBe("GET");
  });

  it("lets a super admin save the global rule", async () => {
    answer = () => res(checklist({ can_set_company_rule: true, can_set_global_rule: true }));
    await show();
    answer = (_url, method) => (method === "PUT" ? res({ block_sourcing: true }) : res(checklist({ can_set_company_rule: true, can_set_global_rule: true, blocking: { on: true, company_rule: null, global_rule: true } })));
    fireEvent.change(screen.getByLabelText("Rule for every other company"), { target: { value: "block" } });
    await screen.findByText("The global rule is saved.");
    expect(calls.find((c) => c.method === "PUT")).toEqual({ url: "/api/v1/recruiter/requirement-checklist/settings", method: "PUT", body: { block_sourcing: true } });
  });
});

describe("the words around it", () => {
  it("reads a structured refusal's message, so the status form lists the missing items", () => {
    expect(detailMessage({ message: "Complete the checklist. Still needed: Salary budget.", code: "checklist_incomplete", missing: [] })).toBe("Complete the checklist. Still needed: Salary budget.");
    expect(detailMessage({ code: "other" })).toBe("Something went wrong.");
  });

  it("names the new follow-up reason and the history entries", () => {
    expect(reasonLabel("clarification")).toBe("Clarification from the client");
    expect(actionLabel("recruiter_requirement.checklist_item")).toBe("Checklist answer changed");
    expect(actionLabel("recruiter_requirement.checklist_override")).toBe("Checklist overridden");
  });
});
