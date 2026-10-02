import { StrictMode } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
    expect(await screen.findByText("No commissions in this period.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "By status" })).toBeNull();
  });

  it.each([
    [401, { detail: "Not authenticated" }, "Your session has expired. Sign in again."],
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
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side. Please try again.");
  });

  it("refuses a To before From without a request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(EMPTY));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentCommissionReportPanel />);
    await screen.findByText("No commissions in this period.");
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
    expect(await screen.findByText("No commissions in this period.")).toBeInTheDocument();
    resolvers[0](json(FULL));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByRole("heading", { name: "By status" })).toBeNull();
  });
});
