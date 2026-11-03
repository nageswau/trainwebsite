import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FeeAccountCard, type FeeAccount } from "@/components/FeeAccountSummary";
import FeeReminderSettingsPanel, { FEE_REMINDER_SETTINGS_URL } from "@/components/FeeReminderSettingsPanel";

// itc-016 (DEC-SCOPE-357): each installment of the fee account carries a derived Overdue / Due / Paid badge and the reminders sent for
// it (AC8); the IT Admin edits the reminder schedule on the Payments page (F3).
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const ACCOUNT: FeeAccount = {
  enrollment_id: "e1", enrollment_code: "ENR-1", course: "Full Stack Java", batch: "FSJ-Nov", currency: "INR",
  course_fee: 45000, discount_approved: 0, tax: 0, total_payable: 45000, paid_confirmed: 20000, credits: 0, balance: 25000, state: "partially_paid",
  next_due: { amount: 8000, due_date: "2026-11-09" },
  installments: [
    { id: "p0", installment_no: 1, amount: 20000, due_date: "2026-10-01", status: "paid", overdue: false, reminders: [] },
    { id: "p1", installment_no: 2, amount: 8000, due_date: "2026-11-09", status: "pending", overdue: true,
      reminders: [{ kind: "due_soon", offset_days: 3, sent_on: "2026-11-06" }, { kind: "overdue", offset_days: 1, sent_on: "2026-11-10" }] },
    { id: "p2", installment_no: null, amount: 17000, due_date: "2026-12-09", status: "pending", overdue: false, reminders: [] },
  ],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Fee installments (itc-016)", () => {
  it("badges each installment and lists the reminders sent", () => {
    render(<FeeAccountCard account={ACCOUNT} />);
    const list = screen.getByRole("list", { name: "Installments" });
    const [paid, late, later] = within(list).getAllByRole("listitem");
    expect(within(paid).getByText("Paid")).toHaveClass("status");
    expect(paid).toHaveTextContent("Installment 1 · INR 20,000.00 · due 01 Oct 2026");
    expect(within(late).getByText("Overdue")).toHaveClass("status", "error");
    expect(late).toHaveTextContent("Reminders sent: 3 days before due on 06 Nov 2026; 1 day overdue on 10 Nov 2026");
    expect(within(later).getByText("Due")).toHaveClass("status", "pending");
    expect(later).toHaveTextContent("INR 17,000.00 · due 09 Dec 2026");
    expect(later).toHaveTextContent("No reminder sent yet");
  });

  it("renders an older response without installments as before", () => {
    const older: FeeAccount = { ...ACCOUNT, installments: undefined };
    render(<FeeAccountCard account={older} />);
    expect(screen.queryByRole("list", { name: "Installments" })).toBeNull();
  });
});

describe("Fee reminder schedule (itc-016)", () => {
  it("loads the schedule, saves a new one and confirms it", async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === "PUT" ? json({ days_before: 5, overdue_days: [2, 10] }) : json({ days_before: 3, overdue_days: [1, 7, 14] }),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<FeeReminderSettingsPanel />);
    const before = await screen.findByLabelText("Days before the due date");
    expect(before).toHaveValue(3);
    expect(screen.getByLabelText("Days after the due date")).toHaveValue("1, 7, 14");
    fireEvent.change(before, { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText("Days after the due date"), { target: { value: "10, 2" } });
    fireEvent.click(screen.getByRole("button", { name: "Update reminder schedule" }));
    expect(await screen.findByText("Reminder schedule saved. It applies from the next daily run.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe(FEE_REMINDER_SETTINGS_URL);
    expect(JSON.parse(String(init?.body))).toEqual({ days_before: 5, overdue_days: [2, 10] });
    expect(screen.getByLabelText("Days after the due date")).toHaveValue("2, 10");
  });

  it("refuses bad values before sending", async () => {
    const fetchMock = vi.fn(async () => json({ days_before: 3, overdue_days: [1, 7, 14] }));
    vi.stubGlobal("fetch", fetchMock);
    render(<FeeReminderSettingsPanel />);
    fireEvent.change(await screen.findByLabelText("Days after the due date"), { target: { value: "1, x" } });
    fireEvent.click(screen.getByRole("button", { name: "Update reminder schedule" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter up to 6 whole numbers from 1 to 90, separated by commas.");
    fireEvent.change(screen.getByLabelText("Days after the due date"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Days before the due date"), { target: { value: "31" } });
    fireEvent.click(screen.getByRole("button", { name: "Update reminder schedule" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a whole number of days from 0 to 30.");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("explains a server refusal and a failed load", async () => {
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === "PUT" ? json({ detail: "Only the IT Admin can see or change the fee reminder schedule" }, 403) : json({ days_before: 0, overdue_days: [] })));
    render(<FeeReminderSettingsPanel />);
    expect(await screen.findByText(/Reminders are off/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Update reminder schedule" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only the IT Admin can see or change the fee reminder schedule");
    cleanup();
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "x" }, 500)));
    render(<FeeReminderSettingsPanel />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("The reminder schedule could not be loaded. Refresh the page to try again."));
  });
});
