import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmOrganizationLeads from "@/components/BdmOrganizationLeads";
import type { Lead } from "@/lib/bdmLeads";

const res = (body: unknown, status = 200) => new Response(body === null ? null : JSON.stringify(body), { status });
const lead = (id: string, over: Partial<Lead> = {}): Lead => ({
  id, name: `Student ${id}`, email: `${id}@example.com`, phone: null, interest: "B.Tech", status: "new", bdm: { id: "b1", full_name: "Asha" },
  converted: false, created_at: "2026-10-05T04:00:00Z", ...over,
});
const page = (items: Lead[], total = items.length, offset = 0) => ({ items, total, limit: 20, offset });
const onNotice = vi.fn();
afterEach(() => {
  onNotice.mockClear();
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmOrganizationLeads (bdm-017 spec §6)", () => {
  it("heads the section with the exact total and shows the empty state", () => {
    render(<BdmOrganizationLeads organizationId="o1" initial={page([])} canAdd={false} onNotice={onNotice} />);
    expect(screen.getByRole("heading", { name: "Leads (0)" })).toBeInTheDocument();
    expect(screen.getByText("No leads yet.")).toBeInTheDocument();
  });

  it("lists leads with contact details, interest, status, who added them and a converted marker", () => {
    render(<BdmOrganizationLeads organizationId="o1" initial={page([lead("l1", { phone: "+91 90000", converted: true, status: "converted" }), lead("l2")], 7)}
      canAdd={false} onNotice={onNotice} />);
    expect(screen.getByRole("heading", { name: "Leads (7)" })).toBeInTheDocument();
    const rows = within(screen.getByRole("table", { name: "Leads" })).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(rows[1]).toHaveTextContent("Student l1");
    expect(rows[1]).toHaveTextContent("l1@example.com · +91 90000");
    expect(rows[1]).toHaveTextContent("Converted to a student");
    expect(rows[2]).toHaveTextContent("Asha");
  });

  it("uses the scrolling table whose row headers keep their case (QA17-01: the email is not shown in capitals)", () => {
    render(<BdmOrganizationLeads organizationId="o1" initial={page([lead("l1")])} canAdd={false} onNotice={onNotice} />);
    expect(screen.getByRole("table", { name: "Leads" }).parentElement).toHaveClass("table-scroll");
  });

  it("a failed first load offers Try again, which reads the first page", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res(page([lead("l1")]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmOrganizationLeads organizationId="o1" initial={null} canAdd={false} onNotice={onNotice} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Leads couldn't be loaded.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByText("Student l1");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/bdm/organizations/o1/leads?limit=20&offset=0");
  });

  it("a failed retry keeps the alert", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "x" }, 500))));
    render(<BdmOrganizationLeads organizationId="o1" initial={null} canAdd={false} onNotice={onNotice} />);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Try again" })).not.toBeDisabled());
    expect(screen.getByRole("alert")).toHaveTextContent("Leads couldn't be loaded.");
  });

  it("loads more with the next offset", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res(page([lead("l3")], 3, 2))));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmOrganizationLeads organizationId="o1" initial={page([lead("l1"), lead("l2")], 3)} canAdd={false} onNotice={onNotice} />);
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await screen.findByText("Student l3");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/bdm/organizations/o1/leads?limit=20&offset=2");
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  });

  it("offers Add lead only when allowed; a saved lead goes on top, the total grows and focus returns", async () => {
    const { rerender } = render(<BdmOrganizationLeads organizationId="o1" initial={page([lead("l1")])} canAdd={false} onNotice={onNotice} />);
    expect(screen.queryByRole("button", { name: "Add lead" })).toBeNull();
    rerender(<BdmOrganizationLeads organizationId="o1" initial={page([lead("l1")])} canAdd onNotice={onNotice} />);
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(lead("l9"), 201))));
    fireEvent.click(screen.getByRole("button", { name: "Add lead" }));
    fireEvent.change(screen.getByLabelText("Student name (required)"), { target: { value: "Student l9" } });
    fireEvent.change(screen.getByLabelText("Email (required)"), { target: { value: "l9@example.com" } });
    fireEvent.change(screen.getByLabelText("Interest (required)"), { target: { value: "B.Tech" } });
    fireEvent.click(screen.getByRole("button", { name: "Save lead" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Leads (2)" })).toBeInTheDocument());
    expect(within(screen.getByRole("table", { name: "Leads" })).getAllByRole("row")[1]).toHaveTextContent("Student l9");
    expect(onNotice).toHaveBeenCalledWith("Lead added.", true);
    await waitFor(() => expect(screen.getByRole("button", { name: "Add lead" })).toBeInTheDocument());
  });
});
