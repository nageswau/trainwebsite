import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ReminderRulesPage from "@/app/overseas/admin/reminder-rules/page";
import ReminderRules from "@/components/ReminderRules";
import { serverApi } from "@/lib/api";
import { actionLabel, offsetError, offsetUnit, runSummary, type ReminderLogPage, type ReminderRule } from "@/lib/reminderRules";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh, push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/overseas/admin/reminder-rules" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const rule = (over: Partial<ReminderRule>): ReminderRule => ({
  key: "application_deadline", label: "Application deadline approaching", description: "Tells the counselor.", action: "notify", timing: "before",
  min_offset: 0, max_offset: 60, enabled: true, offset_days: 7, notify_student: null, updated_at: null, ...over,
});
const RULES = [rule({}), rule({ key: "offer_deadline", label: "Offer deadline approaching", offset_days: 3, notify_student: true }), rule({ key: "no_response", label: "No response after contact", action: "task", timing: "silent", min_offset: 1, offset_days: 3 })];
const EMPTY_LOG: ReminderLogPage = { items: [], total: 0, limit: 50, offset: 0 };

function ok(data: unknown) {
  return Promise.resolve(new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } }));
}

beforeEach(() => {
  refresh.mockReset();
  vi.stubGlobal("fetch", vi.fn());
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("reminderRules lib", () => {
  it("names the units, the action and the run counts", () => {
    expect(offsetUnit("before")).toBe("days before the date");
    expect(offsetUnit("silent")).toBe("days without a call or stage change");
    expect(actionLabel({ action: "task" })).toBe("Task + notice");
    expect(runSummary({ created: 1, duplicate: 4, skipped: 0, failed: 0, rules: {} })).toBe("1 new reminder · 4 already sent.");
    expect(runSummary({ created: 0, duplicate: 0, skipped: 2, failed: 1, rules: {} })).toBe("0 new reminders · 0 already sent · 2 skipped (no active counselor) · 1 failed.");
  });

  it("checks the offset range", () => {
    expect(offsetError({ min_offset: 1, max_offset: 60 }, "0")).toBe("Choose a whole number from 1 to 60");
    expect(offsetError({ min_offset: 0, max_offset: 30 }, "2.5")).not.toBeNull();
    expect(offsetError({ min_offset: 0, max_offset: 30 }, "")).not.toBeNull();
    expect(offsetError({ min_offset: 0, max_offset: 30 }, "30")).toBeNull();
  });
});

describe("ReminderRules", () => {
  it("shows the student switch only on rules that have one, and the empty log", () => {
    render(<ReminderRules rules={RULES} log={EMPTY_LOG} />);
    expect(within(screen.getByRole("form", { name: "Offer deadline approaching" })).getByLabelText(/Also remind the student/)).toBeChecked();
    expect(within(screen.getByRole("form", { name: "Application deadline approaching" })).queryByLabelText(/Also remind the student/)).toBeNull();
    expect(screen.getByText("No reminder has been sent yet.")).toBeInTheDocument();
  });

  it("refuses an out-of-range offset without calling the API", async () => {
    render(<ReminderRules rules={RULES} log={EMPTY_LOG} />);
    const form = screen.getByRole("form", { name: "No response after contact" });
    const input = within(form).getByLabelText("Days without a call or stage change");
    fireEvent.change(input, { target: { value: "0" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    expect(await within(form).findByText("Choose a whole number from 1 to 60")).toBeInTheDocument();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("saves one rule and says so", async () => {
    vi.mocked(fetch).mockReturnValueOnce(ok(rule({ key: "offer_deadline", offset_days: 5, notify_student: false })));
    render(<ReminderRules rules={RULES} log={EMPTY_LOG} />);
    const form = screen.getByRole("form", { name: "Offer deadline approaching" });
    fireEvent.change(within(form).getByLabelText("Days before the date"), { target: { value: "5" } });
    fireEvent.click(within(form).getByLabelText(/Also remind the student/));
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    expect(await within(form).findByRole("status")).toHaveTextContent("Saved.");
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/v1/overseas-admin/reminder-rules/offer_deadline");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ enabled: true, offset_days: 5, notify_student: false });
    expect(refresh).toHaveBeenCalled();
  });

  it("does not send notify_student on a rule without one", async () => {
    vi.mocked(fetch).mockReturnValueOnce(ok(rule({ enabled: false })));
    render(<ReminderRules rules={RULES} log={EMPTY_LOG} />);
    const form = screen.getByRole("form", { name: "Application deadline approaching" });
    fireEvent.click(within(form).getByLabelText("Rule is on"));
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(JSON.parse(String((vi.mocked(fetch).mock.calls[0][1] as RequestInit).body))).toEqual({ enabled: false, offset_days: 7 });
  });

  it("shows the API's refusal", async () => {
    vi.mocked(fetch).mockReturnValueOnce(Promise.resolve(new Response(JSON.stringify({ detail: "This role cannot perform this operation" }), { status: 403 })));
    render(<ReminderRules rules={RULES} log={EMPTY_LOG} />);
    const form = screen.getByRole("form", { name: "Application deadline approaching" });
    fireEvent.click(within(form).getByRole("button", { name: "Save" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("This role cannot perform this operation");
  });

  it("runs the reminders and reports the counts, and lists the log", async () => {
    vi.mocked(fetch).mockReturnValueOnce(ok({ created: 2, duplicate: 1, skipped: 0, failed: 0, rules: {} }));
    const log: ReminderLogPage = { items: [{ id: "l1", rule_key: "deposit_due", rule_label: "Deposit due", summary: "APP-000001 · Leeds · 27 Oct 2026", task_created: false, recipients: 2, created_at: "2026-10-25T03:00:00Z" }], total: 1, limit: 50, offset: 0 };
    render(<ReminderRules rules={RULES} log={log} />);
    expect(screen.getByRole("cell", { name: "APP-000001 · Leeds · 27 Oct 2026" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Run reminders now" }));
    expect(await screen.findByText("2 new reminders · 1 already sent.")).toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/v1/overseas-admin/reminder-rules/run");
  });
});

describe("ReminderRulesPage", () => {
  it("refuses a counselor", async () => {
    vi.mocked(serverApi).mockResolvedValueOnce({ id: "u", role: "counselor", full_name: "C", division: "overseas" });
    render(await ReminderRulesPage());
    expect(screen.getByText("Overseas Administrator role required")).toBeInTheDocument();
  });

  it("renders the rules for the Overseas Admin", async () => {
    vi.mocked(serverApi).mockResolvedValueOnce({ id: "u", role: "overseas_admin", full_name: "A", division: "overseas" }).mockResolvedValueOnce({ rules: RULES }).mockResolvedValueOnce(EMPTY_LOG);
    render(await ReminderRulesPage());
    expect(screen.getByRole("heading", { level: 2, name: "Reminder rules" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Save" })).toHaveLength(3);
  });
});
