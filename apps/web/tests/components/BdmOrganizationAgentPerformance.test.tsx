import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmOrganizationAgentPerformance from "@/components/BdmOrganizationAgentPerformance";
import type { AgentPerformance } from "@/lib/bdmAgentPerformance";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const step = (key: string, label: string, count: number | null) => ({ key, label, definition: `${label} definition.`, tracked: count !== null, count });
const linked: AgentPerformance = {
  organization_id: "o1", linked: true, agency: { name: "ABC Overseas", prefix: "ABC", status: "active" },
  steps: [step("students", "Students", 80), step("applications", "Applications", 65), step("offers", "Offers", 42), step("visa", "Visa", 30),
    step("enrolled", "Enrolled", 25), step("revenue", "Revenue", null)],
  applications_by_stage: [{ key: "enquiry", label: "Enquiry", count: 20 }, { key: "offer", label: "Offer", count: 45 }, { key: "withdrawn", label: "Withdrawn", count: 3 }],
  visa_applications: 34, as_of: "2026-10-07T10:00:00Z",
};
const unlinked: AgentPerformance = { organization_id: "o1", linked: false, agency: null, steps: [], applications_by_stage: [], visa_applications: null, as_of: "2026-10-07T10:00:00Z" };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmOrganizationAgentPerformance (bdm-022 §4)", () => {
  it("shows the agency and the chain Students → Applications → Offers → Visa → Enrolled with counts and definitions", () => {
    render(<BdmOrganizationAgentPerformance orgId="o1" initial={linked} />);
    const region = screen.getByRole("region", { name: "Agent performance" });
    expect(region).toHaveTextContent("ABC Overseas (ABC)");
    const chain = within(region).getByRole("list", { name: "Agent performance chain" });
    const items = within(chain).getAllByRole("listitem");
    expect(items.map((i) => i.textContent?.match(/^(Students|Applications|Offers|Visa|Enrolled|Revenue)/)?.[0])).toEqual(["Students", "Applications", "Offers", "Visa", "Enrolled", "Revenue"]);
    expect(items[0]).toHaveTextContent("80");
    expect(items[2]).toHaveTextContent("42");
    expect(items[2]).toHaveTextContent("Offers definition.");
    expect(items[3]).toHaveTextContent("of 34 visa applications");
  });

  it("says Revenue is not tracked, never a zero", () => {
    render(<BdmOrganizationAgentPerformance orgId="o1" initial={linked} />);
    const revenue = screen.getAllByRole("listitem").find((i) => i.textContent?.startsWith("Revenue"));
    expect(revenue).toHaveTextContent("Not tracked yet");
    expect(revenue?.querySelector(".pipeline-count")).toBeNull();
  });

  it("drills Applications down by stage behind a disclosure button", () => {
    render(<BdmOrganizationAgentPerformance orgId="o1" initial={linked} />);
    const toggle = screen.getByRole("button", { name: "Show applications by stage" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("table", { name: "Applications by stage" })).toBeNull();
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Hide applications by stage" })).toHaveAttribute("aria-expanded", "true");
    const table = screen.getByRole("table", { name: "Applications by stage" });
    expect(within(table).getByRole("row", { name: /Offer/ })).toHaveTextContent("45");
    expect(within(table).getByRole("row", { name: /Withdrawn/ })).toHaveTextContent("3");
  });

  it("QA22-01: sizes every bar against the largest figure, so more applications than students never overflows", () => {
    const more = { ...linked, steps: [step("students", "Students", 3), step("applications", "Applications", 4), step("revenue", "Revenue", null)] };
    const { container } = render(<BdmOrganizationAgentPerformance orgId="o1" initial={more} />);
    expect([...container.querySelectorAll<HTMLElement>(".pipeline-fill")].map((f) => f.style.width)).toEqual(["75%", "100%"]);
  });

  it("QA22-02: says there are no visa applications instead of 0 of 0", () => {
    render(<BdmOrganizationAgentPerformance orgId="o1" initial={{ ...linked, visa_applications: 0 }} />);
    const visa = screen.getAllByRole("listitem").find((i) => i.textContent?.startsWith("Visa"));
    expect(visa).toHaveTextContent("No visa applications yet.");
    expect(visa).not.toHaveTextContent("of 0 visa applications");
  });

  it("QA22-03: says withdrawn applications are not part of the Applications count", () => {
    render(<BdmOrganizationAgentPerformance orgId="o1" initial={linked} />);
    fireEvent.click(screen.getByRole("button", { name: "Show applications by stage" }));
    expect(screen.getByText("Withdrawn applications are not counted in Applications.")).toBeInTheDocument();
  });

  it("flags a suspended agency in text", () => {
    render(<BdmOrganizationAgentPerformance orgId="o1" initial={{ ...linked, agency: { name: "ABC Overseas", prefix: "ABC", status: "suspended" } }} />);
    expect(screen.getByText(/Suspended — this agency's members can't sign in, so these figures are not changing\./)).toBeInTheDocument();
  });

  it("says an organization without a linked agency is not onboarded yet", () => {
    render(<BdmOrganizationAgentPerformance orgId="o1" initial={unlinked} />);
    const region = screen.getByRole("region", { name: "Agent performance" });
    expect(region).toHaveTextContent("Not onboarded yet. Figures appear once Overseas Admin links the agent organization.");
    expect(within(region).queryByRole("list")).toBeNull();
  });

  it("offers Try again when the first read failed, and shows the figures it then reads", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(res({ detail: "boom" }, 500)).mockResolvedValueOnce(res(linked));
    vi.stubGlobal("fetch", fetch);
    render(<BdmOrganizationAgentPerformance orgId="o1" initial={null} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Unable to load the agent performance.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("list", { name: "Agent performance chain" })).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/v1/bdm/organizations/o1/agent-performance", { method: "GET" });
  });
});
