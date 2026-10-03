import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentReportFilters from "@/components/AgentReportFilters";
import { tabsFor } from "@/lib/agentReports";
import type { AgentReportOptions } from "@/lib/types";

// AGN-020 (DEC-SCOPE-063; spec §6.2): the filter form of one report.

const master = tabsFor("master");
const tab = (key: string, tabs = master) => tabs.find((t) => t.key === key)!;
const options: AgentReportOptions = {
  members: [{ value: "ABC-S001", label: "ABC-S001 Staff One" }, { value: "unassigned", label: "Unassigned" }],
  countries: [{ value: "aland", label: "Aland" }],
  universities: [{ value: "alpha", label: "Alpha University" }],
  intakes: [{ value: "2027-09", label: "Sep 2027" }],
  statuses: [{ value: "withdrawn", label: "Withdrawn" }],
};
const empty = { report: "applications" as const, from: "", to: "", filters: {}, offset: 0 };

function renderFilters(props: Partial<Parameters<typeof AgentReportFilters>[0]> = {}) {
  const onApply = vi.fn();
  const onClear = vi.fn();
  render(<AgentReportFilters tab={tab("applications")} value={empty} options={options} busy={false} fieldError={null} onApply={onApply} onClear={onClear} {...props} />);
  return { onApply, onClear };
}

afterEach(cleanup);

describe("AgentReportFilters", () => {
  it("shows a labelled control for each filter the report offers", () => {
    renderFilters();
    for (const label of ["From", "To", "Staff member", "Country", "University", "Intake", "Status"]) expect(screen.getByLabelText(label)).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Report filters" })).toBeInTheDocument();
  });

  it("shows only what a summary offers", () => {
    renderFilters({ tab: tab("countries") });
    expect(screen.getByLabelText("Staff member")).toBeInTheDocument();
    expect(screen.queryByLabelText("Country")).toBeNull();
  });

  it("never offers staff the staff-member filter", () => {
    renderFilters({ tab: tab("applications", tabsFor("staff")) });
    expect(screen.queryByLabelText("Staff member")).toBeNull();
  });

  it("applies the chosen values", () => {
    const { onApply } = renderFilters();
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-01-01" } });
    fireEvent.change(screen.getByLabelText("Country"), { target: { value: "aland" } });
    fireEvent.change(screen.getByLabelText("Intake"), { target: { value: "2027-09" } });
    fireEvent.submit(screen.getByRole("form", { name: "Report filters" }));
    expect(onApply).toHaveBeenCalledWith({ from: "2026-01-01", to: "", filters: { country: "aland", intake: "2027-09" } });
  });

  it("stops a range that ends before it starts, and says so at the To field", () => {
    const { onApply } = renderFilters();
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-02-02" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-02-01" } });
    fireEvent.submit(screen.getByRole("form", { name: "Report filters" }));
    expect(onApply).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("'To' must be on or after 'From'");
    expect(screen.getByLabelText("To")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("To")).toHaveFocus();
  });

  it("shows a server error at its field and focuses it", () => {
    renderFilters({ fieldError: { field: "country", text: "Unknown country" } });
    expect(screen.getByLabelText("Country")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Country")).toHaveFocus();
    expect(screen.getByRole("alert")).toHaveTextContent("Unknown country");
  });

  it("clears every filter", () => {
    const { onClear } = renderFilters({ value: { ...empty, from: "2026-01-01", filters: { country: "aland" } } });
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(onClear).toHaveBeenCalled();
  });

  it("keeps Apply in place but inert while a report loads", () => {
    const { onApply } = renderFilters({ busy: true });
    const apply = screen.getByRole("button", { name: "Apply" });
    expect(apply).toHaveAttribute("aria-disabled", "true");
    fireEvent.submit(screen.getByRole("form", { name: "Report filters" }));
    expect(onApply).not.toHaveBeenCalled();
  });
});
