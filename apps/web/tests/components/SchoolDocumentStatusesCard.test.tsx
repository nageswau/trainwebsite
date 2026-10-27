import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import SchoolDocumentStatusesCard, { type SchoolDocumentStatuses } from "@/components/SchoolDocumentStatusesCard";

afterEach(cleanup);

const DATA: SchoolDocumentStatuses = {
  student_id: "s1",
  applications: [
    {
      application_id: "a1",
      university_name: "University of Toronto",
      has_checklist: true,
      items: [
        { name: "Passport", required: true, status: "verified", status_label: "Verified" },
        { name: "Grade 12 transcript", required: true, status: "missing", status_label: "Missing" },
        { name: "English test", required: false, status: "reupload_required", status_label: "Re-upload required" },
      ],
    },
    { application_id: "a2", university_name: "Monash University", has_checklist: false, items: [] },
  ],
};

// nehn-039 (D2-D5): read-only document statuses for the four school roles.
describe("SchoolDocumentStatusesCard", () => {
  it("shows each application's documents with required flag and status, and no controls", () => {
    render(<SchoolDocumentStatusesCard data={DATA} />);
    expect(screen.getByRole("heading", { name: "Overseas application documents" })).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Documents for University of Toronto" });
    const rows = within(table).getAllByRole("row").slice(1).map((r) => r.textContent);
    expect(rows).toEqual(["PassportRequiredVerified", "Grade 12 transcriptRequiredMissing", "English testOptionalRe-upload required"]);
    expect(within(table).getByText("Verified")).toHaveClass("status");
    expect(within(table).getByText("Re-upload required")).toHaveClass("status", "error");
    expect(within(table).getByText("Missing")).toHaveClass("status", "pending");
    expect(within(table).getAllByRole("cell")[0]).toHaveAttribute("data-label", "Document");
    expect(screen.getByText("No document checklist yet for this application.")).toBeInTheDocument();
    expect(screen.getByText(/Financial documents are not shown/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("says when no applications are linked", () => {
    render(<SchoolDocumentStatusesCard data={{ student_id: "s1", applications: [] }} />);
    expect(screen.getByText("No overseas applications linked yet.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("says when the statuses could not be loaded", () => {
    render(<SchoolDocumentStatusesCard data={null} headingLevel={3} />);
    expect(screen.getByRole("heading", { level: 3, name: "Overseas application documents" })).toBeInTheDocument();
    expect(screen.getByText("Document statuses couldn't be loaded. Reload the page to try again.")).toBeInTheDocument();
  });
});
