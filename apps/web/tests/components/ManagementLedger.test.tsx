import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LedgerEntryPageView from "@/app/management/ledger/[id]/page";
import LedgerPage from "@/app/management/ledger/page";
import LedgerCategories from "@/components/LedgerCategories";
import LedgerEntryActions from "@/components/LedgerEntryActions";
import LedgerEntryForm from "@/components/LedgerEntryForm";
import ManagementLedger from "@/components/ManagementLedger";
import LedgerShell from "@/components/LedgerShell";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe } from "@/lib/management";
import type { LedgerAutoLine, LedgerCategory, LedgerEntry, LedgerFilters, LedgerOptions, LedgerPage as Page } from "@/lib/managementLedger";
import { elements } from "@/tests/helpers/elementTree";

const router = { replace: vi.fn(), refresh: vi.fn(), push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router, redirect: vi.fn(), usePathname: () => "/management/ledger" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const partner: ManagementMe = { id: "p1", full_name: "Arjun Partner", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const accountant: ManagementMe = { id: "a1", full_name: "Asha Accountant", role: "accountant", tiers: { operational: false, finance: true, partner_only: false } };
const RENT: LedgerCategory = { id: "c1", kind: "expense", nature: "fixed", name: "Office rent", active: true };
const TRAVEL: LedgerCategory = { id: "c2", kind: "expense", nature: "variable", name: "Travel", active: true };
const FEES: LedgerCategory = { id: "c3", kind: "income", nature: null, name: "IT training", active: true };
const OLD: LedgerCategory = { id: "c4", kind: "expense", nature: "fixed", name: "Old phone line", active: false };
const filters: LedgerFilters = { month: "", kind: "", category: "", vertical: "", status: "", include: "", offset: 0 };
const can = { edit: true, submit: true, decide: false, reverse: false };

function entry(overrides: Partial<LedgerEntry> = {}): LedgerEntry {
  return {
    id: "e1", entry_date: "2026-10-01", kind: "expense", category: { id: "c1", name: "Office rent", active: true }, amount: "120000.00",
    description: "Office rent for October", vertical: "shared", channel: null, program: null, batch: null, status: "draft", reversal_of_id: null,
    reversed_by_id: null, receipt: null, created_by: { id: "a1", full_name: "Asha Accountant" }, updated_by: { id: "a1", full_name: "Asha Accountant" },
    decided_by: null, submitted_at: null, decided_at: null, rejection_reason: null, created_at: "2026-10-01T04:30:00Z", updated_at: "2026-10-01T04:30:00Z",
    can, ...overrides,
  };
}
const page = (overrides: Partial<Page> = {}): Page => ({
  items: [entry(), entry({ id: "e2", kind: "income", category: { id: "c3", name: "IT training", active: true }, amount: "50000.00", description: "Corporate batch fee", vertical: "it", status: "approved" })],
  total: 2, limit: 25, offset: 0, totals: { income: "50000.00", expense: "0.00", net: "50000.00" }, ...overrides,
});
const options: LedgerOptions = {
  categories: [RENT, TRAVEL, FEES],
  channels: [{ value: "google", label: "Google" }, { value: "instagram", label: "Instagram" }],
  verticals: [{ value: "abroad", label: "Abroad Education" }, { value: "it", label: "IT Training" }, { value: "shared", label: "Shared (company-wide)" }],
  programs: [{ id: "p1", name: "Python Full Stack", batches: [{ id: "b1", name: "PFS Oct" }] }, { id: "p2", name: "Data Science", batches: [{ id: "b2", name: "DS Nov" }] }],
};

type Call = { url: string; method: string; body: unknown };
let calls: Call[];
function respond(...answers: { status?: number; body?: unknown }[]) {
  const queue = [...answers];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({ url, method: init.method ?? "GET", body: init.body instanceof FormData ? init.body : init.body ? JSON.parse(String(init.body)) : undefined });
    const answer = queue.shift() ?? { body: { id: "e9" } };
    return new Response(JSON.stringify(answer.body ?? {}), { status: answer.status ?? 200, headers: { "Content-Type": "application/json" } });
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
  vi.mocked(serverApi).mockReset();
});

describe("mgmt-004 ledger list", () => {
  it("shows the approved totals and each entry with its status, amount and link", () => {
    render(<ManagementLedger data={page()} error="" filters={filters} categories={[RENT, FEES]} />);
    const totals = screen.getByRole("list", { name: "Approved totals" });
    expect(within(totals).getAllByRole("listitem").map((tile) => tile.textContent)).toEqual([
      "Approved income₹50,000.00", "Approved expenses₹0.00", "Net (income − expenses)₹50,000.00",
    ]);
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows[0].textContent).toContain("Office rent for October");
    expect(rows[0].textContent).toContain("₹1,20,000.00");
    expect(rows[0].textContent).toContain("Draft");
    expect(within(rows[0]).getByRole("link", { name: "Office rent for October" }).getAttribute("href")).toBe("/management/ledger/e1");
    expect(rows[1].textContent).toContain("Approved");
  });

  it("keeps the filters in a GET form and offers every category, inactive ones marked", () => {
    render(<ManagementLedger data={page()} error="" filters={{ ...filters, category: "c4", status: "submitted" }} categories={[RENT, OLD]} />);
    const form = screen.getByRole("form", { name: "Ledger filters" });
    expect(form.getAttribute("method")).toBe("get");
    const category = screen.getByRole("combobox", { name: "Category" }) as HTMLSelectElement;
    expect([...category.options].map((o) => o.textContent)).toEqual(["All categories", "Office rent", "Old phone line (inactive)"]);
    expect(category.value).toBe("c4");
    expect((screen.getByRole("combobox", { name: "Status" }) as HTMLSelectElement).value).toBe("submitted");
  });

  it("says when nothing matches, and pages through long lists", () => {
    const { unmount } = render(<ManagementLedger data={page({ items: [], total: 0 })} error="" filters={filters} categories={[]} />);
    expect(screen.getByRole("status").textContent).toBe("No ledger entries match these filters.");
    unmount();
    render(<ManagementLedger data={page({ total: 60, offset: 25 })} error="" filters={{ ...filters, status: "approved", offset: 25 }} categories={[]} />);
    expect(screen.getByRole("link", { name: "Previous page" }).getAttribute("href")).toBe("/management/ledger?status=approved");
    expect(screen.getByRole("link", { name: "Next page" }).getAttribute("href")).toBe("/management/ledger?status=approved&offset=50");
  });
});

describe("mgmt-005 automatic lines in the list", () => {
  const fee: LedgerAutoLine = {
    source: "payment", id: "p1", entry_date: "2026-10-05", kind: "income", vertical: "it", category_label: "IT training", amount: "32500.00", currency: "INR",
    description: "Enrolment fee · receipt RCP-1", counted: true,
  };
  const gbp: LedgerAutoLine = {
    source: "university_commission", id: "u1", entry_date: "2026-10-04", kind: "income", vertical: "abroad", category_label: "University commission",
    amount: "300.00", currency: "GBP", description: "Oxbridge · UC-9", counted: false,
  };
  const mixed = page({
    items: [entry(), fee, gbp], total: 3,
    totals: { income: "32500.00", expense: "0.00", net: "32500.00", not_counted: [{ currency: "GBP", kind: "income", amount: "300.00", count: 1 }] },
  });

  it("offers manual-only or manual + automatic lines, keeping the choice", () => {
    render(<ManagementLedger data={mixed} error="" filters={{ ...filters, include: "auto" }} categories={[]} />);
    const lines = screen.getByRole("combobox", { name: "Lines" }) as HTMLSelectElement;
    expect([...lines.options].map((o) => [o.value, o.textContent])).toEqual([["", "Manual entries only"], ["auto", "Manual + automatic"]]);
    expect(lines.value).toBe("auto");
  });

  it("shows an automatic line read-only with its source badge, label and money", () => {
    render(<ManagementLedger data={mixed} error="" filters={{ ...filters, include: "auto" }} categories={[]} />);
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(within(rows[1]).queryByRole("link")).toBeNull();
    expect(rows[1].textContent).toContain("Enrolment fee · receipt RCP-1");
    expect(rows[1].textContent).toContain("Automatic · Student payment · Income");
    expect(rows[1].textContent).toContain("IT training");
    expect(rows[1].textContent).toContain("IT Training");
    expect(within(rows[1]).getByText("Automatic").className).toBe("badge");
    expect(rows[1].textContent).toContain("₹32,500.00");
    expect(rows[2].textContent).toContain("£300.00");
    expect(rows[2].textContent).toContain("Not counted");
    expect(within(rows[0]).getByRole("link", { name: "Office rent for October" })).toBeTruthy();
  });

  it("names the totals and lists what was not counted", () => {
    render(<ManagementLedger data={mixed} error="" filters={{ ...filters, include: "auto" }} categories={[]} />);
    const totals = screen.getByRole("list", { name: "Totals" });
    expect(within(totals).getAllByRole("listitem").map((tile) => tile.textContent)).toEqual([
      "Income (approved + automatic)₹32,500.00", "Expenses (approved + automatic)₹0.00", "Net (income − expenses)₹32,500.00",
    ]);
    expect(screen.getByText(/Not counted \(not in rupees\)/).textContent).toBe("Not counted (not in rupees): £300.00 income (1 line).");
  });
});

describe("mgmt-004 ledger page", () => {
  const route = (me: ManagementMe, list: () => Promise<unknown>) =>
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/management/me") return me as never;
      if (path === "/api/v1/management/ledger/categories") return { items: [RENT] } as never;
      return list() as never;
    });
  const shellOf = (tree: ReturnType<typeof elements>) => tree.find((el) => el.type === LedgerShell)!;
  const shown = (tree: ReturnType<typeof elements>) => <>{shellOf(tree).props.actions as React.ReactNode}{shellOf(tree).props.children}</>;

  it("reads the filters into the API call; a partner gets the approval queue link", async () => {
    route(partner, async () => page());
    const tree = elements(await LedgerPage({ searchParams: Promise.resolve({ month: "2026-10", offset: "25" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/ledger?month=2026-10&offset=25&limit=25");
    render(shown(tree));
    expect(screen.getByRole("link", { name: "Awaiting approval" }).getAttribute("href")).toBe("/management/ledger?status=submitted");
    expect(screen.getByRole("link", { name: "New entry" }).getAttribute("href")).toBe("/management/ledger/new");
  });

  it("gives the accountant no approval queue link", async () => {
    route(accountant, async () => page());
    render(shown(elements(await LedgerPage({ searchParams: Promise.resolve({}) }))));
    expect(screen.queryByRole("link", { name: "Awaiting approval" })).toBeNull();
  });

  it("shows the access card when the API refuses the caller (super admin)", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/management/me") return { id: "s1", full_name: "Root", role: "super_admin", tiers: { operational: true, finance: false, partner_only: false } } as never;
      if (path.startsWith("/api/v1/management/ledger")) throw new ApiError("Finance access required", 403);
      return { id: "s1", full_name: "Root", role: "super_admin", division: "global" } as never; // the access card's session lookup
    });
    render(await LedgerPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
  });

  it("shows a generic message when the ledger cannot be read", async () => {
    route(partner, () => Promise.reject(new ApiError("boom", 500)));
    render(shown(elements(await LedgerPage({ searchParams: Promise.resolve({}) }))));
    expect(screen.getByRole("alert").textContent).toBe("The ledger is unavailable right now. Please try again.");
  });
});

describe("mgmt-004 entry page", () => {
  it("shows the fields, receipt link, reversal link, history and a step notice", async () => {
    const detail = {
      ...entry({ status: "approved", reversed_by_id: "r1", channel: "exhibition_event", receipt: { name: "rent.pdf", content_type: "application/pdf" }, decided_by: { id: "p2", full_name: "Meera Partner" }, decided_at: "2026-10-02T04:30:00Z", can: { edit: false, submit: false, decide: false, reverse: false } }),
      events: [{ id: "v1", at: "2026-10-01T04:30:00Z", actor: { id: "a1", full_name: "Asha Accountant" }, event: "rejected", from_status: "submitted", to_status: "rejected", fields: [], reason: "No receipt" }],
    };
    vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/management/me" ? partner : detail) as never);
    const tree = elements(await LedgerEntryPageView({ params: Promise.resolve({ id: "e1" }), searchParams: Promise.resolve({ notice: "submit" }) }));
    const shell = tree.find((el) => el.type === LedgerShell)!;
    render(<>{shell.props.children}</>);
    expect(screen.getByRole("alert").textContent).toBe("The entry was saved as a draft, but it could not be submitted. Submit it below.");
    expect(screen.getByRole("link", { name: "Download receipt (rent.pdf)" }).getAttribute("href")).toBe("/api/v1/management/ledger/e1/receipt");
    expect(screen.getByRole("link", { name: "open the reversal" }).getAttribute("href")).toBe("/management/ledger/r1");
    expect(screen.getByText("Approved by")).toBeTruthy();
    expect(screen.getByText("Exhibition/Event")).toBeTruthy(); // QA-04: the channel's label, not its key
    expect(within(screen.getByRole("region", { name: "History" })).getByText(/No receipt/)).toBeTruthy();
  });
});

describe("mgmt-004 entry form", () => {
  const fill = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

  it("checks the required fields before sending anything", async () => {
    respond();
    render(<LedgerEntryForm options={options} today="2026-10-12" />);
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    expect(await screen.findByText("Choose a category")).toBeTruthy();
    expect(screen.getByText("Enter an amount more than 0")).toBeTruthy();
    expect(screen.getByText("Describe the entry (2-500 characters)")).toBeTruthy();
    expect(screen.getByText("Choose a vertical")).toBeTruthy();
    expect(calls).toEqual([]);
  });

  it("offers only the kind's categories and the channel for expenses only", () => {
    render(<LedgerEntryForm options={options} today="2026-10-12" />);
    const category = screen.getByLabelText("Category") as HTMLSelectElement;
    expect([...category.options].map((o) => o.textContent)).toEqual(["Choose…", "Office rent (fixed)", "Travel (variable)"]);
    expect(screen.getByLabelText("Marketing channel (optional)")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Income"));
    expect([...(screen.getByLabelText("Category") as HTMLSelectElement).options].map((o) => o.textContent)).toEqual(["Choose…", "IT training"]);
    expect(screen.queryByLabelText("Marketing channel (optional)")).toBeNull();
  });

  it("saves and submits a new entry, then opens it", async () => {
    respond({ status: 201, body: { id: "e9" } }, { body: { id: "e9" } });
    render(<LedgerEntryForm options={options} today="2026-10-12" />);
    fill("Category", "c1");
    fill("Amount (₹)", "1,20,000");
    fill("Vertical", "shared");
    fill("Description", "Office rent for October");
    fill("Course (optional)", "p1");
    fill("Batch (optional)", "b1");
    fireEvent.click(screen.getByRole("button", { name: "Save and submit" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/management/ledger/e9"));
    expect(calls.map((c) => `${c.method} ${c.url}`)).toEqual(["POST /api/v1/management/ledger", "POST /api/v1/management/ledger/e9/submit"]);
    expect(calls[0].body).toEqual({ kind: "expense", entry_date: "2026-10-12", category_id: "c1", amount: "120000", vertical: "shared",
      description: "Office rent for October", channel: null, program_id: "p1", batch_id: "b1" });
  });

  it("puts the API's 422 on its field", async () => {
    respond({ status: 422, body: { detail: [{ loc: ["body", "amount"], msg: "Value error, The amount is too large", type: "value_error" }] } });
    render(<LedgerEntryForm options={options} today="2026-10-12" />);
    fill("Category", "c1");
    fill("Amount (₹)", "9999999999999");
    fill("Vertical", "it");
    fill("Description", "Too much");
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    expect(await screen.findByText("The amount is too large")).toBeTruthy();
    expect(screen.getByLabelText("Amount (₹)").getAttribute("aria-invalid")).toBe("true");
    expect(router.push).not.toHaveBeenCalled();
  });

  it("uploads a chosen receipt after saving; a failed upload still opens the saved entry with a notice", async () => {
    respond({ status: 201, body: { id: "e9" } }, { status: 415, body: { detail: "Upload a PDF, JPEG or PNG file" } });
    render(<LedgerEntryForm options={options} today="2026-10-12" />);
    fill("Category", "c1");
    fill("Amount (₹)", "500");
    fill("Vertical", "shared");
    fill("Description", "Courier");
    fireEvent.change(screen.getByLabelText("Receipt (optional)"), { target: { files: [new File(["x"], "r.txt", { type: "text/plain" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/management/ledger/e9?notice=receipt"));
    expect(calls[1].method).toBe("PUT");
    expect(calls[1].url).toBe("/api/v1/management/ledger/e9/receipt");
  });

  it("edits an entry with PATCH and keeps its inactive category selectable", async () => {
    respond({ body: { id: "e1" } });
    render(<LedgerEntryForm options={options} today="2026-10-12" entry={entry({ category: { id: "c4", name: "Old phone line", active: false } })} />);
    expect((screen.getByLabelText("Category") as HTMLSelectElement).value).toBe("c4");
    expect(screen.queryByLabelText("Income")).toBeNull(); // the kind never changes
    fill("Amount (₹)", "118000");
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/management/ledger/e1"));
    expect(calls[0].method).toBe("PATCH");
    expect((calls[0].body as Record<string, unknown>).amount).toBe("118000");
    expect(calls[0].body).not.toHaveProperty("kind");
  });
});

describe("mgmt-004 entry actions", () => {
  it("submits a draft and refreshes the page", async () => {
    respond({ body: { id: "e1" } });
    render(<LedgerEntryActions entry={entry()} />);
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
    expect(calls[0]).toEqual({ url: "/api/v1/management/ledger/e1/submit", method: "POST", body: undefined });
    expect(screen.getByRole("link", { name: "Edit" }).getAttribute("href")).toBe("/management/ledger/e1/edit");
  });

  it("lets a partner approve, or reject with a reason", async () => {
    respond({ body: { id: "e1" } });
    const submitted = entry({ status: "submitted", can: { edit: false, submit: false, decide: true, reverse: false } });
    const { unmount } = render(<LedgerEntryActions entry={submitted} />);
    expect(screen.queryByRole("link", { name: "Edit" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(calls[0]?.url).toBe("/api/v1/management/ledger/e1/approve"));
    unmount();
    calls = [];
    respond({ body: { id: "e1" } });
    render(<LedgerEntryActions entry={submitted} />);
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm rejection" }));
    expect(await screen.findByText("Give a reason (2-500 characters)")).toBeTruthy();
    expect(calls).toEqual([]);
    fireEvent.change(screen.getByLabelText("Reason for rejecting"), { target: { value: "Amount differs from the invoice" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm rejection" }));
    await waitFor(() => expect(calls[0]?.body).toEqual({ reason: "Amount differs from the invoice" }));
  });

  it("reverses an approved entry and opens the reversal", async () => {
    respond({ status: 201, body: { id: "r1" } });
    render(<LedgerEntryActions entry={entry({ status: "approved", can: { edit: false, submit: false, decide: false, reverse: true } })} />);
    fireEvent.click(screen.getByRole("button", { name: "Reverse" }));
    fireEvent.change(screen.getByLabelText("Reason for reversing"), { target: { value: "Duplicate entry" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm reversal" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/management/ledger/r1"));
    expect(calls[0]).toEqual({ url: "/api/v1/management/ledger/e1/reverse", method: "POST", body: { reason: "Duplicate entry" } });
  });

  it("keeps the confirmation when the refreshed entry leaves no action (QA-01)", async () => {
    respond({ body: { id: "e1" } });
    const { rerender } = render(<LedgerEntryActions entry={entry()} />);
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
    rerender(<LedgerEntryActions entry={entry({ status: "submitted", can: { edit: false, submit: false, decide: false, reverse: false } })} />);
    expect(screen.getByRole("status").textContent).toBe("Submitted for approval.");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows the server's refusal", async () => {
    respond({ status: 409, body: { detail: "Only a submitted entry can be approved or rejected" } });
    render(<LedgerEntryActions entry={entry({ status: "submitted", can: { edit: false, submit: false, decide: true, reverse: false } })} />);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Only a submitted entry can be approved or rejected");
    expect(router.refresh).not.toHaveBeenCalled();
  });
});

describe("mgmt-004 categories", () => {
  it("lists categories by kind with inactive ones marked", () => {
    render(<LedgerCategories categories={[RENT, OLD, FEES]} />);
    const expense = screen.getByRole("table", { name: "Expense categories" });
    expect(within(expense).getAllByRole("row").slice(1).map((r) => r.textContent)).toEqual([
      expect.stringContaining("Office rent"), expect.stringContaining("Inactive"),
    ]);
    expect(within(screen.getByRole("table", { name: "Income categories" })).getByText("IT training")).toBeTruthy();
  });

  it("adds an expense category with its type, and shows a duplicate refusal", async () => {
    respond({ status: 409, body: { detail: "A category with this name already exists" } }, { status: 201, body: { id: "c9" } });
    render(<LedgerCategories categories={[RENT]} />);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Courier" } });
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "variable" } });
    fireEvent.click(screen.getByRole("button", { name: "Add category" }));
    expect((await screen.findByRole("alert")).textContent).toBe("A category with this name already exists");
    fireEvent.click(screen.getByRole("button", { name: "Add category" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
    expect(calls[1].body).toEqual({ kind: "expense", nature: "variable", name: "Courier" });
  });

  it("deactivates and renames", async () => {
    respond({ body: { id: "c1" } }, { body: { id: "c1" } });
    render(<LedgerCategories categories={[RENT]} />);
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Office rent" }));
    await waitFor(() => expect(calls[0]?.body).toEqual({ active: false }));
    fireEvent.click(screen.getByRole("button", { name: "Rename Office rent" }));
    fireEvent.change(screen.getByLabelText("New name for Office rent"), { target: { value: "Office & warehouse rent" } });
    fireEvent.click(screen.getByRole("button", { name: "Save name" }));
    await waitFor(() => expect(calls[1]?.body).toEqual({ name: "Office & warehouse rent" }));
    expect(calls[1].url).toBe("/api/v1/management/ledger/categories/c1");
  });
});
