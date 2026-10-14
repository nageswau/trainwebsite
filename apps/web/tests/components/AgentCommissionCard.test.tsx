import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AgentCommissionCard from "@/components/AgentCommissionCard";
import { formatAgentCommission } from "@/lib/agentCommission";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); refresh.mockClear(); });

const URL = "/api/v1/partnership/universities/u1/agent-commission";
const call = (fetchMock: ReturnType<typeof vi.fn>) => fetchMock.mock.calls[0] as unknown as [string, RequestInit];

describe("agent commission", () => {
  it("formats percent, fixed and empty", () => {
    expect(formatAgentCommission({ percent: "16.00", amount: null, currency: null, note: null })).toBe("16.00%");
    expect(formatAgentCommission({ percent: null, amount: "4000.00", currency: "GBP", note: "4000GBP flat" })).toBe("GBP 4,000.00");
    expect(formatAgentCommission(null)).toBe("—");
  });
  it("read-only without canEdit", () => {
    render(<AgentCommissionCard universityId="u1" value={{ percent: "13.00", amount: null, currency: null, note: "0.13" }} canEdit={false} />);
    expect(screen.getByText("13.00%")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save agent commission" })).toBeNull();
  });
  it("saves a percent with PUT", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ university: {} })));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentCommissionCard universityId="u1" value={null} canEdit />);
    fireEvent.change(screen.getByLabelText("Percent"), { target: { value: "16" } });
    fireEvent.click(screen.getByRole("button", { name: "Save agent commission" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = call(fetchMock);
    expect(url).toBe(URL);
    expect(init.method).toBe("PUT");
    expect(JSON.parse(String(init.body))).toEqual({ percent: "16" });
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });
  it("saves a fixed amount with currency and note", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ university: {} })));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentCommissionCard universityId="u1" value={null} canEdit />);
    fireEvent.click(screen.getByLabelText("Fixed amount"));
    fireEvent.change(screen.getByLabelText("Amount"), { target: { value: "4000" } });
    fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "GBP" } });
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: "flat" } });
    fireEvent.click(screen.getByRole("button", { name: "Save agent commission" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.parse(String(call(fetchMock)[1].body))).toEqual({ amount: "4000", currency: "GBP", note: "flat" });
  });
  it("Clear calls DELETE, not PUT", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ university: {} })));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("confirm", vi.fn(() => true));
    render(<AgentCommissionCard universityId="u1" value={{ percent: "13.00", amount: null, currency: null, note: null }} canEdit />);
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = call(fetchMock);
    expect(url).toBe(URL);
    expect(init.method).toBe("DELETE");
    expect(init.body).toBeUndefined();
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });
  it("Clear does nothing when the confirmation is declined", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const confirm = vi.fn(() => false);
    vi.stubGlobal("confirm", confirm);
    render(<AgentCommissionCard universityId="u1" value={{ percent: "13.00", amount: null, currency: null, note: null }} canEdit />);
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(confirm).toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
  });
  it("a keyed remount shows the new server value, so a stale rate is not resubmitted", () => {
    const keyed = (v: { percent: string; amount: null; currency: null; note: null }) => <AgentCommissionCard key={JSON.stringify(v)} universityId="u1" value={v} canEdit />;
    const { rerender } = render(keyed({ percent: "13.00", amount: null, currency: null, note: null }));
    expect((screen.getByLabelText("Percent") as HTMLInputElement).value).toBe("13.00");
    rerender(keyed({ percent: "20.00", amount: null, currency: null, note: null }));
    expect((screen.getByLabelText("Percent") as HTMLInputElement).value).toBe("20.00");
  });
  it("shows the API detail in an alert on failure", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "The university is inactive." }), { status: 409 })));
    render(<AgentCommissionCard universityId="u1" value={null} canEdit />);
    fireEvent.change(screen.getByLabelText("Percent"), { target: { value: "16" } });
    fireEvent.click(screen.getByRole("button", { name: "Save agent commission" }));
    expect((await screen.findByRole("alert")).textContent).toContain("The university is inactive.");
    expect(refresh).not.toHaveBeenCalled();
  });
});
