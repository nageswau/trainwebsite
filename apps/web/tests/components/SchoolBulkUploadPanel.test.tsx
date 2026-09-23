import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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

  // QA2-05: a rejected row's reason is shown in the coordinator's words, like the single-student form.
  it("shows each rejected row's reason in the user's words", async () => {
    vi.stubGlobal("crypto", { ...crypto, randomUUID: () => "k1" });
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      id: "b1", status: "completed", total_rows: 2, accepted_count: 1, rejected_count: 1,
      rows: [
        { row_number: 1, status: "accepted", error_message: null, created_student_id: "s1" },
        { row_number: 2, status: "rejected", error_message: "roll_number '5' is already used in this grade and section for this academic year", created_student_id: null },
      ],
    }), { status: 201 })));
    render(<SchoolBulkUploadPanel />);
    fireEvent.change(screen.getByLabelText("Filled-in roster file"), { target: { files: [new File(["full_name\nA\n"], "r.csv", { type: "text/csv" })] } });
    fireEvent.submit(screen.getByLabelText("Filled-in roster file").closest("form")!);
    expect(await screen.findByRole("cell", { name: "Roll number 5 is already used in this grade and section for this academic year" })).toBeTruthy();
    vi.unstubAllGlobals();
  });
});
