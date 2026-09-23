import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SchoolBulkUploadPanel from "@/components/SchoolBulkUploadPanel";

// ENH-025 -- the bulk-upload page documents every template column (spec §4.6, AC6).
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
afterEach(cleanup);

describe("SchoolBulkUploadPanel column reference (ENH-025)", () => {
  it("lists every template column, which are required, and the photo exception", () => {
    render(<SchoolBulkUploadPanel />);
    expect(screen.getByText("Column reference")).toBeTruthy();
    for (const name of ["full_name", "grade_level", "section", "roll_number", "global_education_interest", "preferred_courses"]) {
      expect(screen.getByRole("cell", { name })).toBeTruthy();
    }
    expect(screen.getAllByRole("row")).toHaveLength(18); // header + 17 columns
    expect(screen.getByText(/Photos can't be uploaded in the CSV/)).toBeTruthy();
  });
});
