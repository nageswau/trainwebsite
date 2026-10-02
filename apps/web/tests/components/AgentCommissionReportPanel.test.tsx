import { StrictMode } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentCommissionReportPanel from "@/components/AgentCommissionReportPanel";
import { CSV_URL, REPORT_URL, type CommissionReport } from "@/lib/agentCommissionReport";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const EMPTY: CommissionReport = { date_from: null, date_to: null, totals: [], by_status: [], by_university: [], by_country: [], by_intake: [] };
const FULL: CommissionReport = {
  date_from: null,
  date_to: null,
  totals: [{ currency: "INR", count: 2, amount: 3500 }],
  by_status: [
    { status: "payout_pending", currency: "INR", count: 1, amount: 2000 },
    { status: "paid", currency: "INR", count: 1, amount: 1500 },
  ],
  by_university: [{ university: "Alpha U", country: "Aland", currency: "INR", count: 2, amount: 3500 }],
  by_country: [{ country: "Aland", currency: "INR", count: 2, amount: 3500 }],
  by_intake: [{ intake: "Sep 2027", currency: "INR", count: 2, amount: 3500 }],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/"); // QA14-06 tests put the range in the address
});

describe("AgentCommissionReportPanel (AGN-014)", () => {
  it("shows loading, then the totals and four breakdown tables", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(FULL));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentCommissionReportPanel />);
    expect(screen.getByText("Loading commission report…")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "By status" })).toBeInTheDocument();
    for (const name of ["By university", "By country", "By intake"]) expect(screen.getByRole("heading", { name })).toBeInTheDocument();
    expect(screen.getByText("Payout pending")).toBeInTheDocument();
    expect(screen.getByText(/INR 3,500 \(2 commissions\)/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(REPORT_URL, { credentials: "same-origin" });
  });

  it("says so when there are no commissions", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(EMPTY)));
    render(<AgentCommissionReportPanel />);
    expect(await screen.findByText("Your agency has no commissions yet.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "By status" })).toBeNull();
  });

  it.each([
    [401, { detail: "Not authenticated" }, "Your session has expired."],
    [403, { detail: "Only an agency Master can view commissions" }, "Only an agency Master can view commissions"],
    [500, { detail: "boom" }, "Something went wrong on our side. Please try again."],
  ])("shows a %s as an alert", async (status, body, text) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(body, status)));
    render(<AgentCommissionReportPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(screen.queryByRole("button", { name: "Download CSV" })).toBeNull();
  });

  it("shows a network failure as an alert", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    render(<AgentCommissionReportPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The report could not load. Check your connection and try again."); // QA14-07
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("refuses a To before From without a request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(EMPTY));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentCommissionReportPanel />);
    await screen.findByText("Your agency has no commissions yet.");
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-09-30" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-09-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("'To' must be on or after 'From'.");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("applies the filter and downloads the CSV for the applied range", async () => {
    const fetchMock = vi.fn((url: string) =>
      Promise.resolve(url.startsWith(CSV_URL) ? new Response("a,b", { status: 200, headers: { "content-type": "text/csv" } }) : json(FULL)),
    );
    vi.stubGlobal("fetch", fetchMock);
    URL.createObjectURL = vi.fn(() => "blob:csv");
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<AgentCommissionReportPanel />);
    await screen.findByRole("heading", { name: "By status" });
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-09-01" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-09-30" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledWith(`${REPORT_URL}?date_from=2026-09-01&date_to=2026-09-30`, { credentials: "same-origin" }));
    await screen.findByRole("heading", { name: "By status" });
    fireEvent.click(screen.getByRole("button", { name: "Download CSV" }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledWith(`${CSV_URL}?date_from=2026-09-01&date_to=2026-09-30`, { credentials: "same-origin" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Report downloaded.");
  });

  // --- Frontend review (frontend-ui-engineering), F1-F6 ---

  it("spans the action grid so its tables are not squeezed (F1)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(FULL)));
    const { container } = render(<AgentCommissionReportPanel />);
    await screen.findByRole("heading", { name: "By status" });
    expect(container.firstElementChild).toHaveClass("action-card", "commission-report");
  });

  it("offers Try again after a load error, which reloads the same range (F2)", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json({ detail: "boom" }, 500)).mockResolvedValueOnce(json(FULL));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentCommissionReportPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "By status" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(2, REPORT_URL, { credentials: "same-origin" });
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("keeps the current figures on screen while a new range loads (F3)", async () => {
    let finish: (r: Response) => void = () => {};
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(FULL))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { finish = resolve; }));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentCommissionReportPanel />);
    await screen.findByRole("heading", { name: "By status" });
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-09-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByText("Updating commission report…")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "By status" })).toBeInTheDocument();
    finish(json(EMPTY));
    expect(await screen.findByText("No commissions in this period.")).toBeInTheDocument();
  });

  it("ties the range error to the To field and moves focus there (F4)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(EMPTY)));
    render(<AgentCommissionReportPanel />);
    await screen.findByText("Your agency has no commissions yet.");
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-09-30" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-09-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    const to = screen.getByLabelText("To");
    expect(to).toHaveAttribute("aria-invalid", "true");
    expect(to).toHaveAccessibleDescription("'To' must be on or after 'From'.");
    expect(to).toHaveFocus();
    fireEvent.change(to, { target: { value: "2026-10-01" } });
    expect(to).not.toHaveAttribute("aria-invalid");
  });

  it("words the empty state for a filtered range (F5)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json(EMPTY)))); // a fresh Response per call: a body reads once
    render(<AgentCommissionReportPanel />);
    await screen.findByText("Your agency has no commissions yet.");
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-09-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByText("No commissions in this period.")).toBeInTheDocument();
  });

  it("groups digits Indian-style for INR only (F6)", async () => {
    const report: CommissionReport = { ...EMPTY, totals: [{ currency: "INR", count: 1, amount: 100000 }, { currency: "USD", count: 1, amount: 100000 }] };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(report)));
    render(<AgentCommissionReportPanel />);
    expect(await screen.findByText(/INR 1,00,000 \(1 commission\) · USD 100,000 \(1 commission\)/)).toBeInTheDocument();
  });

  // --- Browser QA (2026-10-02), QA14-02/03/05/06/08/09/10 ---

  it("shows compact, named tables with the amount next to the label, and the CSV action before them (QA14-02/03/09)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(FULL)));
    render(<AgentCommissionReportPanel />);
    const table = await screen.findByRole("table", { name: "By status" });
    for (const name of ["By university", "By country", "By intake"]) expect(screen.getByRole("table", { name })).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Search all columns...")).toBeNull();
    expect(screen.queryByText("Rows per page")).toBeNull();
    expect(within(table).getAllByRole("columnheader").map((th) => th.textContent)).toEqual(["Status", "Amount", "Count"]);
    expect(within(table).getAllByRole("row")[1]).toHaveTextContent("Payout pendingINR 2,0001");
    // Every breakdown is three columns so it fits a 320 px phone; the university's country rides in its cell.
    const universities = screen.getByRole("table", { name: "By university" });
    expect(within(universities).getAllByRole("columnheader").map((th) => th.textContent)).toEqual(["University", "Amount", "Count"]);
    expect(within(universities).getAllByRole("row")[1]).toHaveTextContent("Alpha U (Aland)INR 3,5002");
    const csv = screen.getByRole("button", { name: "Download CSV" });
    expect(csv.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("keeps the figures and offers no retry when the server rejects the range (QA14-05)", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json(FULL)).mockResolvedValueOnce(json({ detail: "date_to must be before 9999-12-31" }, 422));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentCommissionReportPanel />);
    await screen.findByRole("table", { name: "By status" });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "9999-12-31" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("'To' must be before 9999-12-31");
    expect(screen.getByRole("table", { name: "By status" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("offers a sign-in link back to this page, not a retry, when the session has expired (QA14-08)", async () => {
    window.history.replaceState(null, "", "/overseas/agent/reports?from=2026-09-01");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "Not authenticated" }, 401)));
    render(<AgentCommissionReportPanel />);
    const link = await screen.findByRole("link", { name: "Sign in again" });
    expect(link).toHaveAttribute("href", `/overseas/login?next=${encodeURIComponent("/overseas/agent/reports?from=2026-09-01")}`);
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("restores the range from the address and records an applied range there (QA14-06)", async () => {
    window.history.replaceState(null, "", "/overseas/agent/reports?from=2026-09-01&to=2026-09-30");
    const fetchMock = vi.fn(() => Promise.resolve(json(FULL)));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentCommissionReportPanel />);
    await screen.findByRole("table", { name: "By status" });
    expect(fetchMock).toHaveBeenCalledWith(`${REPORT_URL}?date_from=2026-09-01&date_to=2026-09-30`, { credentials: "same-origin" });
    expect(screen.getByLabelText("From")).toHaveValue("2026-09-01");
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await vi.waitFor(() => expect(window.location.search).toBe("?from=2026-09-01"));
  });

  it("ignores a malformed range in the address (QA14-06)", async () => {
    window.history.replaceState(null, "", "/overseas/agent/reports?from=yesterday&to=2026-9-1");
    const fetchMock = vi.fn(() => Promise.resolve(json(EMPTY)));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentCommissionReportPanel />);
    await screen.findByText("Your agency has no commissions yet.");
    expect(fetchMock).toHaveBeenCalledWith(REPORT_URL, { credentials: "same-origin" });
  });

  it("offers no CSV when there is nothing to export (QA14-10)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(EMPTY)));
    render(<AgentCommissionReportPanel />);
    await screen.findByText("Your agency has no commissions yet.");
    expect(screen.queryByRole("button", { name: "Download CSV" })).toBeNull();
  });

  it("ignores a response that arrives after a newer one", async () => {
    const resolvers: ((r: Response) => void)[] = [];
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => resolvers.push(resolve))));
    render(
      <StrictMode>
        <AgentCommissionReportPanel />
      </StrictMode>,
    ); // StrictMode runs the mount effect twice: two requests in flight
    await vi.waitFor(() => expect(resolvers.length).toBe(2));
    resolvers[1](json(EMPTY));
    expect(await screen.findByText("Your agency has no commissions yet.")).toBeInTheDocument();
    resolvers[0](json(FULL));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByRole("heading", { name: "By status" })).toBeNull();
  });
});
