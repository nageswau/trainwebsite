import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import FundingRecordsCard from "@/components/FundingRecordsCard";
import type { FundingRecord } from "@/lib/fundingRecords";

afterEach(cleanup);

const OPEN: FundingRecord = {
  id: "f1", school_student_id: "s1", support_type: "education_loan", status: "application", status_changed_on: "2026-09-20",
  provider_name: "State Bank of India", amount_text: "₹5,00,000", notes: "Bank asked for\nfee receipts", closure_reason: null,
  created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-20T00:00:00Z", counselor_name: "Anita", updated_by_name: "Ravi",
};
const CLOSED: FundingRecord = { ...OPEN, id: "f2", support_type: "scholarship", status: "closed", provider_name: null, amount_text: null, notes: "", closure_reason: "Not eligible this year", updated_by_name: null };

// ENH-020 (spec §6, SCR-SCH-042): the read-only view for parents, coordinators and principals.
describe("FundingRecordsCard", () => {
  it("shows each case's type, stage in words and details, with no controls", () => {
    render(<FundingRecordsCard records={[OPEN, CLOSED]} />);
    expect(screen.getByRole("heading", { name: "Funding support" })).toBeInTheDocument();
    const lists = screen.getAllByRole("definition").map((d) => d.textContent);
    expect(lists).toContain("Education loan");
    expect(lists.some((t) => t?.startsWith("Stage 4 of 6 · Application"))).toBe(true);
    expect(lists).toContain("State Bank of India");
    expect(lists).toContain("₹5,00,000");
    expect(lists).toContain("Ravi");
    expect(lists).toContain("Not eligible this year");
    expect(screen.getByText(/Bank asked for/)).toHaveClass("funding-notes");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("leaves out details that were never recorded", () => {
    render(<FundingRecordsCard records={[CLOSED]} />);
    const terms = screen.getAllByRole("term").map((t) => t.textContent);
    expect(terms).not.toContain("Provider");
    expect(terms).not.toContain("Amount");
    expect(terms).not.toContain("Notes");
    expect(terms).toContain("Reason closed");
  });

  it("says when there are no cases", () => {
    render(<FundingRecordsCard records={[]} />);
    expect(screen.getByText("No funding support cases for this student.")).toBeInTheDocument();
  });

  it("says the section could not load instead of breaking the page", () => {
    render(<FundingRecordsCard records={null} />);
    expect(screen.getByText("Funding support cases couldn't be loaded. Reload the page to try again.")).toBeInTheDocument();
  });

  it("uses the heading level of the page it sits on", () => {
    render(<FundingRecordsCard records={[]} headingLevel={2} />);
    expect(within(document.body).getByRole("heading", { level: 2, name: "Funding support" })).toBeInTheDocument();
  });
});
