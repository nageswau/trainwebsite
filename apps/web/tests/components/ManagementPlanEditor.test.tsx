import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ManagementPlanEditor from "@/components/ManagementPlanEditor";
import ManagementPlanForm from "@/components/ManagementPlanForm";
import type { PlanDetail, PlanItem, PlanOptions } from "@/lib/managementPlans";

const router = { replace: vi.fn(), refresh: vi.fn(), push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router, redirect: vi.fn(), usePathname: () => "/management/plans/2026-11" }));

const PARTNER = { id: "u1", full_name: "Arjun Partner", role: "partner" };
const BDM = { id: "u2", full_name: "Uma BDM", role: "partnership_manager" };
const options: PlanOptions = {
  kpis: [{ key: "agents", label: "New agents", unit: "count", definition: "Agencies created in the month" }, { key: "revenue", label: "Revenue (₹)", unit: "inr", definition: "P&L revenue" }],
  verticals: [{ key: "abroad", label: "Abroad Education" }, { key: "it", label: "IT Training" }],
  users: [PARTNER, BDM], current_month: "2026-10", max_month: "2027-10",
};

function item(overrides: Partial<PlanItem> = {}): PlanItem {
  return { id: "i1", vertical: "abroad", text: "Sign Korean universities", kpi: null, target: null, done: false, task_count: 0, updated_at: "2026-10-01T04:30:00Z", ...overrides };
}
function plan(overrides: Partial<PlanDetail> = {}): PlanDetail {
  return {
    id: "p1", month: "2026-11", status: "active", label: "November 2026", item_count: 2, kpi_count: 1, done_count: 0, created_by: PARTNER, updated_at: "2026-10-01T04:30:00Z",
    items: [item(), item({ id: "i2", text: "Recruit 30 new agents", kpi: "agents", target: "30.00" })], ...overrides,
  };
}

type Call = { url: string; method: string; body: unknown };
let calls: Call[];
let release: () => void = () => {};
function respond(...answers: { status?: number; body?: unknown; hold?: boolean }[]) {
  const queue = [...answers];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({ url, method: init.method ?? "GET", body: init.body ? JSON.parse(String(init.body)) : undefined });
    const answer = queue.shift() ?? { body: { id: "x" } };
    if (answer.hold) await new Promise<void>((resolve) => { release = resolve; });
    return new Response(answer.status === 204 ? null : JSON.stringify(answer.body ?? {}), { status: answer.status ?? 200, headers: { "Content-Type": "application/json" } });
  }));
}

beforeEach(() => {
  calls = [];
  router.push.mockReset();
  router.refresh.mockReset();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("mgmt-026 plan editor", () => {
  it("lists items under their vertical, with an empty vertical said so", () => {
    render(<ManagementPlanEditor plan={plan()} options={options} today="2026-10-14" />);
    const abroad = screen.getByRole("region", { name: "Abroad Education (2)" });
    expect(within(abroad).getByText("Sign Korean universities")).toBeTruthy();
    expect(within(abroad).getByText(/New agents · Target 30/)).toBeTruthy();
    expect(within(screen.getByRole("region", { name: "IT Training (0)" })).getByText("No items in this vertical.")).toBeTruthy();
  });

  it("adds a KPI item with its target, then refreshes", async () => {
    respond({ status: 201, body: { id: "i3" } });
    render(<ManagementPlanEditor plan={plan()} options={options} today="2026-10-14" />);
    const form = screen.getByRole("form", { name: "Add item" });
    fireEvent.change(within(form).getByLabelText("Vertical"), { target: { value: "it" } });
    fireEvent.change(within(form).getByLabelText("Item"), { target: { value: "  500 new   students " } });
    fireEvent.change(within(form).getByLabelText("KPI"), { target: { value: "agents" } });
    fireEvent.change(within(form).getByLabelText("Target"), { target: { value: "500" } });
    fireEvent.click(within(form).getByRole("button", { name: "Add item" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
    expect(calls).toEqual([{ url: "/api/v1/management/plans/2026-11/items", method: "POST", body: { vertical: "it", text: "500 new students", kpi: "agents", target: "500" } }]);
  });

  it("sends a free-text item without a KPI or target, and puts a 422 on its field", async () => {
    respond({ status: 422, body: { detail: [{ loc: ["body", "text"], msg: "Value error, The item must be 2-200 characters" }] } });
    render(<ManagementPlanEditor plan={plan()} options={options} today="2026-10-14" />);
    const form = screen.getByRole("form", { name: "Add item" });
    expect(within(form).queryByLabelText("Target")).toBeNull();
    fireEvent.change(within(form).getByLabelText("Item"), { target: { value: "Sign Japanese universities" } });
    fireEvent.click(within(form).getByRole("button", { name: "Add item" }));
    await waitFor(() => expect(within(form).getByText("The item must be 2-200 characters")).toBeTruthy());
    expect(calls[0].body).toEqual({ vertical: "abroad", text: "Sign Japanese universities" });
    expect(router.refresh).not.toHaveBeenCalled();
  });

  it("blocks a double submit while the first add is in flight", async () => {
    respond({ status: 201, body: { id: "i3" }, hold: true });
    render(<ManagementPlanEditor plan={plan()} options={options} today="2026-10-14" />);
    const form = screen.getByRole("form", { name: "Add item" });
    fireEvent.change(within(form).getByLabelText("Item"), { target: { value: "Sign Japanese universities" } });
    fireEvent.submit(form);
    fireEvent.submit(form);
    await waitFor(() => expect(calls).toHaveLength(1));
    release();
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
    expect(calls).toHaveLength(1);
  });

  it("toggles a free-text item done (AC3)", async () => {
    respond({ body: { id: "i1", done: true } });
    render(<ManagementPlanEditor plan={plan()} options={options} today="2026-10-14" />);
    fireEvent.click(screen.getByRole("checkbox", { name: "Done: Sign Korean universities" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
    expect(calls).toEqual([{ url: "/api/v1/management/plans/2026-11/items/i1", method: "PATCH", body: { done: true } }]);
    expect(screen.queryByRole("checkbox", { name: "Done: Recruit 30 new agents" })).toBeNull(); // a KPI item is never "done"
  });

  it("QA-01: shows the tick at once while saving, and takes it back if the save fails", async () => {
    respond({ status: 409, body: { detail: "This plan is closed. Reopen it to change it." }, hold: true });
    render(<ManagementPlanEditor plan={plan()} options={options} today="2026-10-14" />);
    const box = screen.getByRole("checkbox", { name: "Done: Sign Korean universities" }) as HTMLInputElement;
    fireEvent.click(box);
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(box.checked).toBe(true);
    release();
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("This plan is closed. Reopen it to change it."));
    expect(box.checked).toBe(false);
  });

  it("edits an item sending only what changed; clearing the KPI clears its target", async () => {
    respond({ body: { id: "i2" } });
    render(<ManagementPlanEditor plan={plan()} options={options} today="2026-10-14" />);
    fireEvent.click(screen.getByRole("button", { name: "Edit Recruit 30 new agents" }));
    const form = screen.getByRole("form", { name: "Edit Recruit 30 new agents" });
    fireEvent.change(within(form).getByLabelText("KPI"), { target: { value: "" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
    expect(calls).toEqual([{ url: "/api/v1/management/plans/2026-11/items/i2", method: "PATCH", body: { kpi: null, target: null } }]);
  });

  it("removes an item after confirming", async () => {
    respond({ status: 204 });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<ManagementPlanEditor plan={plan()} options={options} today="2026-10-14" />);
    fireEvent.click(screen.getByRole("button", { name: "Remove Sign Korean universities" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
    expect(calls).toEqual([{ url: "/api/v1/management/plans/2026-11/items/i1", method: "DELETE", body: undefined }]);
  });

  it("creates a task from an item", async () => {
    respond({ status: 201, body: { id: "t1" } });
    render(<ManagementPlanEditor plan={plan()} options={options} today="2026-10-14" />);
    fireEvent.click(screen.getByRole("button", { name: "Create task from Sign Korean universities" }));
    const form = screen.getByRole("form", { name: "Task for Sign Korean universities" });
    fireEvent.change(within(form).getByLabelText("Owner"), { target: { value: "u2" } });
    fireEvent.change(within(form).getByLabelText("Deadline"), { target: { value: "2026-10-20" } });
    fireEvent.click(within(form).getByRole("button", { name: "Create task" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Task created for Uma BDM"));
    expect(calls).toEqual([{ url: "/api/v1/management/plans/2026-11/items/i1/tasks", method: "POST", body: { owner_user_id: "u2", priority: "medium", deadline: "2026-10-20" } }]);
  });

  it("changes the plan status", async () => {
    respond({ body: { id: "p1", status: "closed" } });
    render(<ManagementPlanEditor plan={plan()} options={options} today="2026-10-14" />);
    fireEvent.change(screen.getByLabelText("Plan status"), { target: { value: "closed" } });
    fireEvent.click(screen.getByRole("button", { name: "Update status" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
    expect(calls).toEqual([{ url: "/api/v1/management/plans/2026-11", method: "PATCH", body: { status: "closed" } }]);
  });

  it("a closed plan is read-only until reopened", () => {
    render(<ManagementPlanEditor plan={plan({ status: "closed" })} options={options} today="2026-10-14" />);
    expect(screen.getByText("This plan is closed. Reopen it to change it.")).toBeTruthy();
    expect(screen.queryByRole("form", { name: "Add item" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Edit / })).toBeNull();
    expect((screen.getByRole("checkbox", { name: "Done: Sign Korean universities" }) as HTMLInputElement).disabled).toBe(true);
  });
});

describe("mgmt-026 plan a month", () => {
  it("offers only unplanned months in the window and opens the new plan", async () => {
    respond({ status: 201, body: { id: "p2", month: "2026-12" } });
    render(<ManagementPlanForm first="2026-10" last="2027-01" planned={["2026-11"]} />);
    const choices = within(screen.getByLabelText("Month")).getAllByRole("option").map((o) => o.getAttribute("value"));
    expect(choices).toEqual(["2026-10", "2026-12", "2027-01"]);
    fireEvent.change(screen.getByLabelText("Month"), { target: { value: "2026-12" } });
    fireEvent.click(screen.getByRole("button", { name: "Plan this month" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/management/plans/2026-12"));
    expect(calls).toEqual([{ url: "/api/v1/management/plans", method: "POST", body: { month: "2026-12" } }]);
  });

  it("says so when every month in the window is planned", () => {
    render(<ManagementPlanForm first="2026-10" last="2026-11" planned={["2026-10", "2026-11"]} />);
    expect(screen.getByText("Every month you can plan already has a plan.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Plan this month" })).toBeNull();
  });
});
