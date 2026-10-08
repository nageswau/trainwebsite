import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import UniversityMatchList from "@/components/UniversityMatchList";
import type { UniversityMatch } from "@/lib/universities";

afterEach(cleanup);

const MATCH: UniversityMatch = {
  id: "u1", university_code: "UNV-000012", name: "ABC University", country: { id: "gb", name: "United Kingdom" }, city: "London",
  active: true, catalogue_visible: false, existing_relationship: "existing",
  primary_manager: { id: "m1", full_name: "Rahul Nair", active: true }, backup_manager: { id: "m2", full_name: "Asha Rao", active: false },
};

describe("UniversityMatchList (upc-004 UD5)", () => {
  it("shows the five panel fields, with dashes where nothing is tracked yet", () => {
    render(<UniversityMatchList matches={[MATCH]} total={1} linkable />);
    const item = screen.getByRole("listitem");
    expect(within(item).getByRole("link", { name: "UNV-000012 · ABC University" })).toHaveAttribute("href", "/partnership/universities/u1");
    expect(item).toHaveTextContent("United Kingdom · London · Internal");
    expect(item).toHaveTextContent("Existing relationshipExisting");
    expect(item).toHaveTextContent("Assigned managerRahul Nair (primary), Asha Rao (backup, inactive)");
    for (const term of ["Current stage", "Last contact", "Next follow-up"]) expect(item).toHaveTextContent(`${term}—`);
    expect(item).toHaveStyle({ color: "var(--ink)" }); // QA-02: plain text even inside a red alert
  });

  it("names an unassigned university, counts hidden matches and renders an action without links", () => {
    const action = vi.fn();
    const unowned = { ...MATCH, id: "u2", primary_manager: null, backup_manager: null, existing_relationship: null, active: false };
    render(<UniversityMatchList matches={[unowned]} total={3} action={(m) => <button type="button" onClick={() => action(m.id)}>Link</button>} />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByRole("listitem")).toHaveTextContent("Assigned managerUnassigned");
    expect(screen.getByRole("listitem")).toHaveTextContent("Inactive");
    expect(screen.getByText("2 more matching universities.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Link" }));
    expect(action).toHaveBeenCalledWith("u2");
  });
});
