import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import Departments from "@/components/Departments";
import SalaryGrid from "@/components/SalaryGrid";
import type { SalaryMonth, SalaryRow } from "@/lib/salaries";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row = (over: Partial<SalaryRow> = {}): SalaryRow => ({
  department: { id: "d1", name: "Training", active: true }, entered: true, headcount: 4, payable: "200000.00", paid: "180000.00",
  incentives: "15000.00", commissions: "5000.00", employer_cost: "20000.00", total_cost: "220000.00", warnings: [], ...over,
});
const blankRow = (id: string, name: string): SalaryRow => ({
  department: { id, name, active: true }, entered: false, headcount: null, payable: null, paid: null, incentives: null, commissions: null,
  employer_cost: null, total_cost: null, warnings: [],
});
const month = (over: Partial<SalaryMonth> = {}): SalaryMonth => ({
  month: "2026-09", current_month: "2026-10", rows: [row(), blankRow("d2", "Marketing")],
  totals: { headcount: 4, payable: "200000.00", paid: "180000.00", incentives: "15000.00", commissions: "5000.00", employer_cost: "20000.00", total_cost: "220000.00" },
  revenue: "800000.00", ratio: "27.50", updated_at: "2026-10-01T10:00:00Z", updated_by: { id: "u", full_name: "Asha Accountant" }, ...over,
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("SalaryGrid (mgmt-011 §9)", () => {
  it("shows the seven figures, the employee cost, revenue and the ratio", () => {
    render(<SalaryGrid data={month()} />);
    const figures = screen.getByRole("list", { name: "Salary figures for September 2026" }).textContent ?? "";
    for (const text of ["Total employees", "4", "Salary payable", "₹2,00,000.00", "Salary paid", "₹1,80,000.00", "Incentives", "Commissions", "Employer cost"]) {
      expect(figures).toContain(text);
    }
    const cost = screen.getByRole("region", { name: "Employee cost ratio" });
    expect(cost.id).toBe("employee-cost");
    expect(cost.textContent).toContain("₹2,20,000.00");
    expect(cost.textContent).toContain("₹8,00,000.00");
    expect(cost.textContent).toContain("27.50%");
  });

  it("shows a dash for the ratio without revenue", () => {
    render(<SalaryGrid data={month({ revenue: "0.00", ratio: null })} />);
    expect(within(screen.getByRole("region", { name: "Employee cost ratio" })).getByText("—")).toBeTruthy();
  });

  it("lists every department with labelled inputs and the totals row", () => {
    render(<SalaryGrid data={month()} />);
    const table = screen.getByRole("table", { name: "Salaries by department" });
    expect((screen.getByLabelText("Salary paid for Training") as HTMLInputElement).value).toBe("180000.00");
    expect((screen.getByLabelText("Employees for Marketing") as HTMLInputElement).value).toBe("");
    const rows = within(table).getAllByRole("row");
    expect(rows.at(-1)?.textContent).toContain("₹2,20,000.00");
  });

  it("warns when paid is more than payable while typing", () => {
    render(<SalaryGrid data={month()} />);
    fireEvent.change(screen.getByLabelText("Salary paid for Training"), { target: { value: "250000" } });
    expect(screen.getByText("Paid is more than payable")).toBeTruthy();
  });

  it("saves the month once, says so and refreshes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res(month()));
    vi.stubGlobal("fetch", fetchMock);
    render(<SalaryGrid data={month()} />);
    fireEvent.change(screen.getByLabelText("Employees for Marketing"), { target: { value: "2" } });
    const save = screen.getByRole("button", { name: "Save September 2026" });
    fireEvent.click(save);
    fireEvent.click(save);
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Salaries for September 2026 saved."));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/management/salaries?month=2026-09");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body).rows.map((r: { department_id: string }) => r.department_id)).toEqual(["d1", "d2"]);
    expect(refresh).toHaveBeenCalled();
  });

  it("puts a 422 on its department row", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: [{ loc: ["body", "rows", 0, "paid"], msg: "An amount can't be negative" }] }, 422)));
    render(<SalaryGrid data={month()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save September 2026" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Check the highlighted departments"));
    expect(screen.getByText("Salary paid: An amount can't be negative")).toBeTruthy();
    expect(screen.getByLabelText("Salary paid for Training").getAttribute("aria-invalid")).toBe("true");
  });

  it("says how to start when there are no departments", () => {
    render(<SalaryGrid data={month({ rows: [] })} />);
    expect(screen.getByText(/No departments yet/)).toBeTruthy();
  });
});

describe("Departments (mgmt-011 SM1/SM2)", () => {
  const list = [{ id: "d1", name: "Training", active: true }, { id: "d9", name: "Old team", active: false }];

  it("adds a department and refreshes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ id: "d3", name: "Design", active: true }, 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<Departments departments={list} />);
    fireEvent.change(screen.getByLabelText("New department"), { target: { value: " Design " } });
    fireEvent.click(screen.getByRole("button", { name: "Add department" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Design added."));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ name: "Design" });
    expect(refresh).toHaveBeenCalled();
  });

  it("checks the name length before sending and shows a 409", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ detail: "A department with this name already exists" }, 409));
    vi.stubGlobal("fetch", fetchMock);
    render(<Departments departments={list} />);
    fireEvent.click(screen.getByRole("button", { name: "Add department" }));
    expect(screen.getByRole("alert").textContent).toBe("Use 2-80 characters");
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("New department"), { target: { value: "Training" } });
    fireEvent.click(screen.getByRole("button", { name: "Add department" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("A department with this name already exists"));
  });

  it("renames, deactivates and reactivates", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({}));
    vi.stubGlobal("fetch", fetchMock);
    render(<Departments departments={list} />);
    fireEvent.click(screen.getByRole("button", { name: "Rename Training" }));
    fireEvent.change(screen.getByLabelText("New name for Training"), { target: { value: "Training & Delivery" } });
    fireEvent.click(screen.getByRole("button", { name: "Save name" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Name saved."));
    fireEvent.click(screen.getByRole("button", { name: "Reactivate Old team" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Old team reactivated."));
    expect(fetchMock.mock.calls.map(([url, init]) => [url, init.method, JSON.parse(init.body)])).toEqual([
      ["/api/v1/management/departments/d1", "PATCH", { name: "Training & Delivery" }],
      ["/api/v1/management/departments/d9", "PATCH", { active: true }],
    ]);
  });
});
