import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ManagementSchoolsPage from "@/app/management/schools/page";
import LedgerEntryForm from "@/components/LedgerEntryForm";
import ManagementSchools from "@/components/ManagementSchools";
import PortalShell from "@/components/PortalShell";
import SchoolValuesEditor from "@/components/SchoolValuesEditor";
import { ApiError, serverApi } from "@/lib/api";
import { formatCalendarDate } from "@/lib/formatDate";
import type { ManagementMe } from "@/lib/management";
import type { LedgerEntry, LedgerOptions } from "@/lib/managementLedger";
import type { SchoolRow, SchoolsDashboard } from "@/lib/managementSchools";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import { elements } from "@/tests/helpers/elementTree";

const router = { replace: vi.fn(), refresh: vi.fn(), push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router, redirect: vi.fn(), usePathname: () => "/management/schools" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const partner: ManagementMe = { id: "p1", full_name: "Priya Partner", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const superAdmin: ManagementMe = { id: "s1", full_name: "Sam Admin", role: "super_admin", tiers: { operational: true, finance: false, partner_only: false } };
const QUERY = { from: "2026-05-01", to: "2026-05-31" };
const LABELS = [
  "Schools contacted", "Meetings", "Proposals", "MoUs", "Active schools", "Students", "Teachers", "Parents", "Career guidance", "Psychometric tests",
  "Academic results", "Student profile completion", "School revenue",
]; // prettier-ignore
const KEYS = [
  "schools_contacted", "meetings", "proposals", "mous", "active_schools", "students", "teachers", "parents", "career_guidance", "psychometric_tests",
  "academic_results", "profile_completion", "revenue",
] as const; // prettier-ignore

const school = (over: Partial<SchoolRow>): SchoolRow => ({
  id: "s1", name: "Green Valley School", tier: "gold", active: true, renewal_due: false, tier_valid_until: "2027-03-31",
  students: 0, teachers: 0, parents: 0, career_guidance: 0, psychometric_tests: 0, academic_results: 0, profile_completion: null,
  revenue: "0.00", contract_value: null, renewal_value: null, ...over,
}); // prettier-ignore

function dashboard(over: Partial<SchoolsDashboard> = {}): SchoolsDashboard {
  return {
    from: "2026-05-01", to: "2026-05-31", as_of: "2026-10-14T05:00:00Z", money_visible: true,
    figures: KEYS.map((key, i) => ({ key, label: LABELS[i], definition: `${LABELS[i]} meaning.`, basis: i < 4 || key === "revenue" ? "period" : "now" })),
    totals: { schools_contacted: 9, meetings: 4, proposals: 3, mous: 2, active_schools: 1, students: 1250, teachers: 6, parents: 30, career_guidance: 40,
              psychometric_tests: 25, academic_results: 12, profile_completion: 46, revenue: "160000.00", contract_value: "250000.00",
              renewal_value: "275000.50", contracts_not_entered: 1 },
    untagged_revenue: "10000.00",
    schools: [
      school({ id: "s1", students: 1200, teachers: 5, parents: 28, career_guidance: 40, psychometric_tests: 25, academic_results: 12, profile_completion: 48,
               revenue: "150000.00", contract_value: "250000.00", renewal_value: "275000.50" }),
      school({ id: "s2", name: "Hill Top Academy", tier: null, active: false, tier_valid_until: null, renewal_due: true, students: 50, teachers: 1, parents: 2 }),
    ],
    ...over,
  }; // prettier-ignore
}

function hidden(): SchoolsDashboard {
  const data = dashboard({ money_visible: false, untagged_revenue: null });
  data.totals = { ...data.totals, revenue: null, contract_value: null, renewal_value: null, contracts_not_entered: null };
  data.schools = data.schools.map((s) => ({ ...s, revenue: null, contract_value: null, renewal_value: null }));
  return data;
}

function view(props: Partial<Parameters<typeof ManagementSchools>[0]> = {}) {
  return render(<ManagementSchools data={dashboard()} error="" query={QUERY} {...props} />);
}

const figures = () => screen.getByRole("list", { name: "School figures" });
const tile = (label: string) => within(figures()).getByText(label, { selector: "span" }).closest("li")!;
const table = () => screen.getByRole("table", { name: "School-wise figures" });
const cells = (row: Element) => Array.from(row.querySelectorAll("td")).map((td) => td.textContent);

type Call = { url: string; method: string; body: unknown };
let calls: Call[];
function respond(...answers: { status?: number; body?: unknown }[]) {
  const queue = [...answers];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({ url, method: init.method ?? "GET", body: init.body ? JSON.parse(String(init.body)) : undefined });
    const answer = queue.shift() ?? { body: {} };
    return new Response(JSON.stringify(answer.body ?? {}), { status: answer.status ?? 200, headers: { "Content-Type": "application/json" } });
  }));
}

beforeEach(() => {
  calls = [];
  vi.mocked(serverApi).mockReset();
  router.refresh.mockReset();
  router.push.mockReset();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("mgmt-022 ManagementSchools", () => {
  it("shows the thirteen §18 figures in source order, with Indian grouping, per cent and rupees", () => {
    view();
    expect(within(figures()).getAllByRole("listitem").map((li) => li.querySelector("span")!.textContent)).toEqual(LABELS);
    expect(tile("Students")).toHaveTextContent("1,250");
    expect(tile("Student profile completion")).toHaveTextContent("46%");
    expect(tile("School revenue")).toHaveTextContent("₹1,60,000.00");
    expect(tile("MoUs")).toHaveTextContent("MoUs meaning.");
  });

  it("lists every school with its figures, money and an editor, the untagged line and an All schools total", () => {
    view();
    expect(within(table()).getAllByRole("columnheader").map((th) => th.textContent)).toEqual([
      "School", "Students", "Teachers", "Parents", "Career guidance", "Psychometric tests", "Academic results", "Profile completion", "Revenue",
      "Contract value", "Renewal value", "Values",
    ]); // prettier-ignore
    const green = within(table()).getByRole("rowheader", { name: /Green Valley School/ }).closest("tr")!;
    expect(green.querySelector(".schools-meta")).toHaveTextContent(`Gold · Active · valid until ${formatCalendarDate("2027-03-31")}`);
    expect(cells(green).slice(0, 10)).toEqual(["1,200", "5", "28", "40", "25", "12", "48%", "₹1,50,000.00", "₹2,50,000.00", "₹2,75,000.50"]);
    const hill = within(table()).getByRole("rowheader", { name: /Hill Top Academy/ }).closest("tr")!;
    expect(hill.querySelector(".schools-meta")).toHaveTextContent("No tier · Not active · Renewal due");
    expect(cells(hill).slice(6, 10)).toEqual(["No students", "₹0.00", "Not entered", "Not entered"]);
    const [untagged, total] = Array.from(table().querySelectorAll("tfoot tr"));
    expect(untagged).toHaveTextContent("Not tagged to a school");
    expect(untagged).toHaveTextContent("₹10,000.00");
    expect(total).toHaveTextContent("All schools");
    expect(total).toHaveTextContent("₹1,60,000.00");
    expect(screen.getByText(/1 of 2 schools have no contract value entered/)).toBeInTheDocument();
    expect(screen.getByLabelText("Edit values for Green Valley School")).toHaveTextContent("Edit values");
    expect(screen.getByRole("heading", { name: "School-wise revenue, contract value and renewal value" }).closest("section")).toHaveAttribute("id", "school-money");
  });

  it("shows the super admin no money: a Finance only tile, no money columns, no editor", () => {
    view({ data: hidden() });
    expect(within(tile("School revenue")).getByText("Finance only")).toHaveClass("metric-untracked");
    expect(within(table()).queryByRole("columnheader", { name: "Revenue" })).toBeNull();
    expect(within(table()).queryByRole("columnheader", { name: "Values" })).toBeNull();
    expect(screen.queryByText("Not tagged to a school")).toBeNull();
    expect(screen.queryByText("Edit values")).toBeNull();
    expect(screen.queryByText(/₹/)).toBeNull();
  });

  it("names the period and the schools, in a GET period form", () => {
    view();
    expect(screen.getByText(new RegExp(`^${formatCalendarDate("2026-05-01")} to ${formatCalendarDate("2026-05-31")}`))).toHaveTextContent("2 schools");
    const form = screen.getByRole("form", { name: "Choose a period" });
    expect(form).toHaveAttribute("method", "get");
    expect(within(form).getByLabelText("From")).toHaveValue("2026-05-01");
    expect(screen.getByRole("link", { name: "This month" })).toHaveAttribute("href", "/management/schools");
  });

  it("says so when there are no schools, and shows an error without figures", () => {
    view({ data: dashboard({ schools: [] }) });
    expect(screen.getByRole("status")).toHaveTextContent("No partner schools yet");
    expect(screen.queryByRole("table")).toBeNull();
    cleanup();
    view({ data: null, error: "The period must start on or before its end" });
    expect(screen.getByRole("alert")).toHaveTextContent("The period must start on or before its end");
    expect(screen.queryByRole("list", { name: "School figures" })).toBeNull();
  });
});

describe("mgmt-022 SchoolValuesEditor", () => {
  const editor = (over: Partial<SchoolRow> = {}) => render(<SchoolValuesEditor school={school({ contract_value: "250000.00", ...over })} />);
  const save = () => fireEvent.click(screen.getByRole("button", { name: "Save" }));

  it("saves both values (empty clears) and refreshes the dashboard", async () => {
    respond({ body: { id: "s1", contract_value: "300000.00", renewal_value: null } });
    editor();
    expect(screen.getByLabelText("Contract value (₹)")).toHaveValue("250000.00");
    fireEvent.change(screen.getByLabelText("Contract value (₹)"), { target: { value: "₹3,00,000" } });
    save();
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
    expect(calls).toEqual([{ url: "/api/v1/management/schools/s1", method: "PATCH", body: { contract_value: "300000", renewal_value: null } }]);
    expect(screen.getByRole("status")).toHaveTextContent("Saved.");
  });

  it("checks amounts before sending, and puts the API's 422 on its field", async () => {
    respond({ status: 422, body: { detail: [{ loc: ["body", "renewal_value"], msg: "Value error, The amount is too large", type: "value_error" }] } });
    editor();
    fireEvent.change(screen.getByLabelText("Contract value (₹)"), { target: { value: "-5" } });
    save();
    expect(await screen.findByText("Enter an amount of 0 or more")).toBeInTheDocument();
    expect(calls).toEqual([]);
    fireEvent.change(screen.getByLabelText("Contract value (₹)"), { target: { value: "10.555" } });
    save();
    expect(await screen.findByText("Use at most 2 decimal places")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Contract value (₹)"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText("Renewal value (₹)"), { target: { value: "9999999999999" } });
    save();
    expect(await screen.findByText("The amount is too large")).toBeInTheDocument();
    expect(screen.getByLabelText("Renewal value (₹)")).toHaveAttribute("aria-invalid", "true");
    expect(router.refresh).not.toHaveBeenCalled();
  });

  it("shows a refusal that has no field", async () => {
    respond({ status: 403, body: { detail: "Finance access required" } });
    editor();
    save();
    expect(await screen.findByRole("alert")).toHaveTextContent("Finance access required");
  });
});

describe("mgmt-022 School dashboard page", () => {
  function answer(me: ManagementMe, result: SchoolsDashboard | Error) {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      const value = path === "/api/v1/management/me" ? me : path.startsWith("/api/v1/management/schools") ? result : (null as never);
      if (value instanceof Error) throw value;
      return value as never;
    });
  }

  it("asks for the period in the address and renders in the Command Center sidebar", async () => {
    answer(partner, dashboard());
    const tree = await ManagementSchoolsPage({ searchParams: Promise.resolve({ from: "2026-05-01", to: "2026-05-31" }) });
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/schools?from=2026-05-01&to=2026-05-31");
    expect(elements(tree).find((el) => el.type === PortalShell)!.props.nav).toContainEqual({ label: "Schools", href: "/management/schools" });
    render(tree);
    expect(screen.getByRole("heading", { name: "School dashboard" })).toBeInTheDocument();
  });

  it("keeps the super admin's own sidebar", async () => {
    answer(superAdmin, hidden());
    const tree = await ManagementSchoolsPage({ searchParams: Promise.resolve({}) });
    expect(elements(tree).find((el) => el.type === PortalShell)!.props.nav).toBe(SUPER_ADMIN_NAV);
  });

  it("shows the API's 422 message, and a generic message on a server error", async () => {
    answer(partner, new ApiError("The period must start on or before its end", 422));
    render(await ManagementSchoolsPage({ searchParams: Promise.resolve({ from: "2026-05-31", to: "2026-05-01" }) }));
    expect(screen.getByRole("alert")).toHaveTextContent("The period must start on or before its end");
    cleanup();
    answer(partner, new ApiError("Internal Server Error", 500));
    render(await ManagementSchoolsPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("alert")).toHaveTextContent("School figures are unavailable right now. Please try again.");
  });
});

describe("mgmt-022 ledger school tag (SD14)", () => {
  const options: LedgerOptions = {
    categories: [{ id: "c3", kind: "income", nature: null, name: "School projects", active: true }, { id: "c1", kind: "expense", nature: "fixed", name: "Office rent", active: true }],
    channels: [],
    verticals: [{ value: "school", label: "School projects" }, { value: "it", label: "IT Training" }],
    programs: [],
    schools: [{ id: "s1", name: "Green Valley School" }],
  };
  const fill = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

  it("offers a school only for School projects income, and sends it", async () => {
    respond({ status: 201, body: { id: "e9" } });
    render(<LedgerEntryForm options={options} today="2026-10-12" />);
    fill("Vertical", "school");
    expect(screen.queryByLabelText("School (optional)")).toBeNull(); // an expense
    fireEvent.click(screen.getByLabelText("Income"));
    fill("Category", "c3");
    fill("Amount (₹)", "40000");
    fill("Description", "Career programme fee");
    fill("School (optional)", "s1");
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/management/ledger/e9"));
    expect((calls[0].body as Record<string, unknown>).school_id).toBe("s1");
  });

  it("drops the school when the vertical changes, and keeps an entry's school when editing", async () => {
    respond({ body: { id: "e1" } });
    const tagged = { kind: "income", vertical: "school", category: { id: "c3", name: "School projects", active: true }, school: { id: "s1", name: "Green Valley School" } } as Partial<LedgerEntry>;
    render(<LedgerEntryForm options={options} today="2026-10-12" entry={{ id: "e1", entry_date: "2026-10-01", amount: "1.00", description: "Fee", channel: null, program: null, batch: null, ...tagged } as LedgerEntry} />);
    expect(screen.getByLabelText("School (optional)")).toHaveValue("s1");
    fill("Vertical", "it");
    expect(screen.queryByLabelText("School (optional)")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(router.push).toHaveBeenCalled());
    expect((calls[0].body as Record<string, unknown>).school_id).toBeNull();
  });
});
