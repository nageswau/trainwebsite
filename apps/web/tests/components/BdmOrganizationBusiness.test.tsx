import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmOrganizationBusiness from "@/components/BdmOrganizationBusiness";
import type { Business } from "@/lib/bdmBusiness";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const stage = (key: string, label: string, count: number | null) => ({ key, label, definition: `${label} definition.`, tracked: count !== null, count });
const line = (key: string, label: string, amount: string | null) => ({ key, label, definition: `${label} rule.`, tracked: amount !== null, amount });
const business = (over: Partial<Business> = {}): Business => ({
  organization_id: "o1", currency: "INR",
  funnel: [stage("contacted", "Contacted", 420), stage("leads", "Leads", 420), stage("registrations", "Registrations", 210), stage("training", "Training", 120),
    stage("certification", "Certification", 80), stage("internship", "Internship", null), stage("placement", "Placement", 30)],
  revenue: { lines: [line("training", "Training fees", "1250000.50"), line("internship", "Internship", null), line("placement", "Placement", null), line("other", "Other", null)] },
  ...over,
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmOrganizationBusiness (bdm-021 spec §5)", () => {
  it("shows each funnel stage's count as text with its written definition", () => {
    render(<BdmOrganizationBusiness organizationId="o1" initial={business()} />);
    expect(screen.getByRole("heading", { name: "Business" })).toBeInTheDocument();
    const stages = within(screen.getByRole("list", { name: "Student funnel" })).getAllByRole("listitem");
    expect(stages.map((s) => s.querySelector(".pipeline-label")?.textContent)).toEqual(
      ["Contacted", "Leads", "Registrations", "Training", "Certification", "Internship", "Placement"]);
    expect(stages[2]).toHaveTextContent("210");
    expect(stages[2]).toHaveTextContent("Registrations definition.");
  });

  it("labels an untracked stage instead of showing a number (AC2)", () => {
    render(<BdmOrganizationBusiness organizationId="o1" initial={business()} />);
    const internship = within(screen.getByRole("list", { name: "Student funnel" })).getAllByRole("listitem")[5];
    expect(internship).toHaveTextContent("Not tracked yet");
    expect(internship.querySelector(".pipeline-count")).toBeNull();
    expect(internship.querySelector(".pipeline-track")).toBeNull();
  });

  it("shows revenue in INR and labels the untracked lines", () => {
    render(<BdmOrganizationBusiness organizationId="o1" initial={business()} />);
    const revenue = screen.getByRole("region", { name: "Revenue (INR)" });
    expect(within(revenue).getByText("₹12,50,000.50")).toBeInTheDocument();
    expect(within(revenue).getAllByText("Not tracked yet")).toHaveLength(3);
    expect(within(revenue).getByText("Training fees rule.")).toBeInTheDocument();
  });

  it("says who can see revenue when the server withholds it (B3)", () => {
    render(<BdmOrganizationBusiness organizationId="o1" initial={business({ revenue: null })} />);
    expect(screen.queryByText(/₹/)).toBeNull();
    expect(screen.getByText("Revenue is visible to the organization's assigned BDM and their manager.")).toBeInTheDocument();
  });

  it("explains an empty funnel when there are no leads yet", () => {
    const empty = business({ funnel: business().funnel.map((s) => ({ ...s, count: s.tracked ? 0 : null })) });
    render(<BdmOrganizationBusiness organizationId="o1" initial={empty} />);
    expect(screen.getByText("No leads yet. The funnel fills in as leads are added and linked to student accounts.")).toBeInTheDocument();
  });

  it("a failed first load offers Try again, which reads the figures", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail: "boom" }, 500)).mockResolvedValueOnce(res(business()));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmOrganizationBusiness organizationId="o1" initial={null} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Business figures couldn't be loaded.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Business figures couldn't be loaded."));
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByRole("list", { name: "Student funnel" })).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/bdm/organizations/o1/business");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
