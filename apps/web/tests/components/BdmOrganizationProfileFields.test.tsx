import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmOrganizationProfileFields, { filledFields, profileErrors, profilePayload, profileValuesOf } from "@/components/BdmOrganizationProfileFields";

afterEach(cleanup);
const blank = profileValuesOf(null);

describe("BdmOrganizationProfileFields (bdm-003 AC1, AC4, §12.2)", () => {
  it("renders exactly each type's fields under a legend, and nothing for common-only types", () => {
    const { rerender, container } = render(<BdmOrganizationProfileFields idPrefix="f" group="school" values={blank} errors={{}} onChange={vi.fn()} />);
    expect(screen.getByRole("group", { name: "School details" })).toBeInTheDocument();
    expect(["Board", "School type", "Lowest grade", "Highest grade"].map((l) => screen.getByLabelText(l).tagName)).toEqual(["SELECT", "SELECT", "SELECT", "SELECT"]);
    expect(screen.getAllByRole("option", { name: "LKG" })[0]).toHaveValue("-1");
    rerender(<BdmOrganizationProfileFields idPrefix="f" group="college" values={blank} errors={{}} onChange={vi.fn()} />);
    expect(screen.getByLabelText("Courses").tagName).toBe("TEXTAREA");
    expect(screen.queryByLabelText("Board")).toBeNull();
    rerender(<BdmOrganizationProfileFields idPrefix="f" group="agent" values={blank} errors={{}} onChange={vi.fn()} />);
    expect(screen.getByLabelText("Number of staff")).toHaveAttribute("inputmode", "numeric");
    expect(screen.getByText("Commission: Available after onboarding").tagName).toBe("P"); // text, never an input
    expect(screen.queryByLabelText(/Commission/)).toBeNull();
    rerender(<BdmOrganizationProfileFields idPrefix="f" group={null} values={blank} errors={{}} onChange={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("reports changes and ties errors to their field", () => {
    const onChange = vi.fn();
    render(<BdmOrganizationProfileFields idPrefix="f" group="school" values={blank} errors={{ grade_to: "Lowest grade can't be above the highest grade" }} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Board"), { target: { value: "CBSE" } });
    expect(onChange).toHaveBeenCalledWith("board", "CBSE");
    expect(screen.getByLabelText("Highest grade")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Highest grade")).toHaveAccessibleDescription("Lowest grade can't be above the highest grade");
  });

  it("builds the create payload from the current group's filled fields only", () => {
    const values = { ...blank, board: "CBSE", grade_from: "6", grade_to: "12", country: "India" };
    expect(profilePayload("school", values)).toEqual({ board: "CBSE", grade_from: 6, grade_to: 12 });
    expect(profilePayload("school", blank)).toBeNull();
    expect(profilePayload(null, values)).toBeNull();
  });

  it("builds the edit payload from changes only and clears with null (Review Focus 3)", () => {
    const original = profileValuesOf({ kind: "school", board: "CBSE", school_type: "private", grade_from: 6, grade_to: 12 });
    expect(original.grade_from).toBe("6");
    expect(profilePayload("school", { ...original, board: "", grade_to: "10" }, original)).toEqual({ board: null, grade_to: 10 });
    expect(profilePayload("school", original, original)).toBeNull();
  });

  it("sends a non-whole number as typed so the server names the field (Review Focus 2)", () => {
    expect(profilePayload("agent", { ...blank, staff_count: "abc" })).toEqual({ staff_count: "abc" });
    expect(profilePayload("agent", { ...blank, staff_count: "6.5" })).toEqual({ staff_count: "6.5" });
    expect(JSON.stringify(profilePayload("agent", { ...blank, staff_count: "12" }))).toBe('{"staff_count":12}');
  });

  it("checks the grade order and lists filled fields", () => {
    expect(profileErrors("school", { ...blank, grade_from: "8", grade_to: "-1" })).toEqual({ grade_to: "Lowest grade can't be above the highest grade" });
    expect(profileErrors("school", { ...blank, grade_from: "-2", grade_to: "0" })).toEqual({});
    expect(filledFields("school", { ...blank, board: "CBSE", affiliation: "VTU" })).toEqual(["board"]);
  });
});
