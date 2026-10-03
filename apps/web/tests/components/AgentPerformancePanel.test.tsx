import { StrictMode } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentPerformancePanel from "@/components/AgentPerformancePanel";
import { PERFORMANCE_URL, type AgentPerformance, type AgentPerformanceCounts } from "@/lib/agentPerformance";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const counts = (s: number[], f: number[]): AgentPerformanceCounts => ({
  students: s[0], applications: s[1], offers: s[2], visa_applications: s[3], visa_approvals: s[4], enrollments: s[5],
  funnel: { students: f[0], applications: f[1], submitted: f[2], offers: f[3], visa: f[4], enrolled: f[5] },
});
const FULL: AgentPerformance = {
  date_from: null,
  date_to: null,
  rows: [
    { code: "ABC-S001", name: "Staff One", active: true, ...counts([2, 5, 3, 1, 1, 1], [3, 3, 2, 2, 1, 1]) },
    { code: "ABC-S002", name: "Staff Two", active: false, ...counts([3, 3, 3, 1, 0, 1], [3, 3, 3, 2, 2, 1]) },
    { code: "ABC-S003", name: "Staff Four", active: true, ...counts([0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0]) },
  ],
  unassigned: counts([1, 1, 1, 0, 0, 0], [1, 1, 1, 1, 0, 0]),
  total: counts([6, 9, 7, 2, 1, 2], [7, 7, 6, 5, 3, 2]),
  as_of: "2026-10-03T05:12:00Z",
};
const EMPTY: AgentPerformance = { ...FULL, rows: [{ ...FULL.rows[2] }], unassigned: null, total: counts([0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0]) };

const stageCounts = () => within(screen.getByRole("list", { name: /^Student funnel/ })).getAllByRole("listitem").map((li) => li.textContent);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

describe("AgentPerformancePanel (AGN-019)", () => {
  it("loads, then shows the agency funnel and the staff table", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(FULL));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentPerformancePanel />);
    expect(screen.getByText("Loading staff performance…")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Funnel" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(PERFORMANCE_URL, { credentials: "same-origin" });
    expect(stageCounts()).toEqual([
      "Students7100% of students",
      "Applications7100% of students",
      "Submitted686% of students",
      "Offers571% of students",
      "Visa343% of students",
      "Enrolled229% of students",
    ]);
    const table = screen.getByRole("region", { name: "By staff member" });
    const rows = within(table).getAllByRole("row").slice(1).map((r) => within(r).getByRole("rowheader").textContent);
    expect(rows).toEqual(["Staff One ABC-S001", "Staff Two ABC-S002 Deactivated", "Staff Four ABC-S003", "Unassigned", "All staff and unassigned"]);
    expect(screen.getByText(/Includes archived students and withdrawn applications/)).toBeInTheDocument();
  });

  it("reads the range from the address and sends it", async () => {
    window.history.replaceState(null, "", "/overseas/agent/performance?from=2026-01-01&to=2026-01-31");
    const fetchMock = vi.fn().mockResolvedValue(json({ ...FULL, date_from: "2026-01-01", date_to: "2026-01-31" }));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentPerformancePanel />);
    await screen.findByRole("heading", { name: "Funnel" });
    expect(fetchMock).toHaveBeenCalledWith(`${PERFORMANCE_URL}?date_from=2026-01-01&date_to=2026-01-31`, { credentials: "same-origin" });
    expect(screen.getByLabelText("From")).toHaveValue("2026-01-01");
  });

  it("switches the funnel without a request, and resets it when a new range loads", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => json(FULL)); // a fresh Response per call: a body reads once
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentPerformancePanel />);
    await screen.findByRole("heading", { name: "Funnel" });
    const select = screen.getByLabelText("Show funnel for");
    fireEvent.change(select, { target: { value: "ABC-S002" } });
    expect(screen.getByRole("list", { name: "Student funnel: Staff Two (ABC-S002) — deactivated" })).toBeInTheDocument();
    expect(stageCounts()[5]).toBe("Enrolled133% of students");
    fireEvent.change(select, { target: { value: "ABC-S003" } });
    expect(stageCounts()[0]).toBe("Students0—"); // no students: no percentage, never NaN
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    await vi.waitFor(() => expect(screen.getByLabelText("Show funnel for")).toHaveValue("agency"));
  });

  it.each([
    [null, "Your agency has no students yet."],
    ["2026-01-01", "No students were added in this period."],
  ])("says so when there are no students (from=%s)", async (from, text) => {
    if (from) window.history.replaceState(null, "", `/overseas/agent/performance?from=${from}`);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(EMPTY)));
    render(<AgentPerformancePanel />);
    expect(await screen.findByText(text)).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: /^Student funnel/ })).toBeNull();
    expect(screen.getByRole("region", { name: "By staff member" })).toBeInTheDocument(); // zeros are information
  });

  it("offers to sign in again on 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "Not authenticated" }, 401)));
    render(<AgentPerformancePanel />);
    expect(await screen.findByRole("link", { name: "Sign in again" })).toBeInTheDocument();
  });

  it("shows the server's refusal on 403", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "Only an agency Master can view staff performance" }, 403)));
    render(<AgentPerformancePanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Only an agency Master can view staff performance");
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("offers Try again on a server error, and it reloads", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json({ detail: "boom" }, 500)).mockResolvedValueOnce(json(FULL));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentPerformancePanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load staff performance.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Funnel" })).toBeInTheDocument();
  });

  it("refuses To before From without a request, on the To field", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(FULL));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentPerformancePanel />);
    await screen.findByRole("heading", { name: "Funnel" });
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-02-01" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(screen.getByText("'To' must be on or after 'From'.")).toBeInTheDocument();
    expect(screen.getByLabelText("To")).toHaveAttribute("aria-invalid", "true");
    expect(document.activeElement).toBe(screen.getByLabelText("To"));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("puts a server date error on the field it names, keeping the figures", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json(FULL)).mockResolvedValueOnce(json({ detail: "date_from must be a date (YYYY-MM-DD)" }, 422));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentPerformancePanel />);
    await screen.findByRole("heading", { name: "Funnel" });
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByText("'From' must be a date (YYYY-MM-DD)")).toBeInTheDocument();
    expect(screen.getByLabelText("From")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("heading", { name: "Funnel" })).toBeInTheDocument();
  });

  it("drops a slower, older response", async () => {
    let releaseFirst: (r: Response) => void = () => {};
    const first = new Promise<Response>((resolve) => (releaseFirst = resolve));
    const fetchMock = vi.fn().mockReturnValueOnce(first).mockResolvedValueOnce(json(EMPTY));
    vi.stubGlobal("fetch", fetchMock);
    // StrictMode mounts twice in development: two loads, the first one slower.
    render(
      <StrictMode>
        <AgentPerformancePanel />
      </StrictMode>,
    );
    expect(await screen.findByText("Your agency has no students yet.")).toBeInTheDocument();
    releaseFirst(json(FULL));
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByRole("heading", { name: "Funnel" })).toBeNull();
  });
});
