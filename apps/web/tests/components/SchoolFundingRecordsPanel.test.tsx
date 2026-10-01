import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), usePathname: () => "/school/career-counselor/funding" }));

import Loading from "@/app/school/career-counselor/funding/loading";
import SchoolFundingRecordsPanel from "@/components/SchoolFundingRecordsPanel";
import type { FundingRecord } from "@/lib/fundingRecords";
import { SCHOOL_NAV } from "@/lib/navigation";

afterEach(cleanup);

const STUDENTS = [
  { id: "s1", full_name: "Asha", school_name: "Hill School" },
  { id: "s2", full_name: "Ravi", school_name: "Hill School" },
];

function makeCase(id: string, overrides: Partial<FundingRecord>): FundingRecord {
  return {
    id, school_student_id: "s1", support_type: "education_loan", status: "documents", status_changed_on: "2026-09-20", provider_name: "HDFC",
    amount_text: null, notes: "", closure_reason: null, created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-20T00:00:00Z",
    counselor_name: "Anita", updated_by_name: null, ...overrides,
  };
}

const OPEN = makeCase("f1", {});
const OPEN_2 = makeCase("f2", { school_student_id: "s2", support_type: "scholarship", status: "required", provider_name: null });
const DONE = makeCase("f3", { status: "closed", closure_reason: "Bank refused" });

// ENH-020 (spec §6): open cases are the counsellor's work, so they come first; finished cases are history, collapsed and read-only.
describe("SchoolFundingRecordsPanel", () => {
  it("lists open cases with their stage in words and keeps finished ones collapsed below", () => {
    render(<SchoolFundingRecordsPanel records={[OPEN, OPEN_2, DONE]} students={STUDENTS} />);
    const open = screen.getByRole("table", { name: "Open cases" });
    const headers = within(open).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Student", "Support type", "Stage", "Since", "Provider", "Actions"]);
    expect(within(open).getAllByRole("row")).toHaveLength(3);
    expect(within(open).getByText("Stage 3 of 6 · Documents")).toBeInTheDocument();
    const finished = screen.getByText("Finished cases (1)").closest("details") as HTMLElement;
    expect(finished).not.toHaveAttribute("open");
    expect(within(finished).getByText("Closed")).toBeInTheDocument();
    expect(within(finished).getByText("Bank refused")).toBeInTheDocument();
    expect(within(finished).queryByRole("button", { name: /Edit/ })).not.toBeInTheDocument();
  });

  it("gives every Edit button a unique accessible name and labels cells for the phone layout", () => {
    render(<SchoolFundingRecordsPanel records={[OPEN, OPEN_2]} students={STUDENTS} />);
    expect(screen.getByRole("button", { name: "Edit education loan case for Asha" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit scholarship case for Ravi" })).toBeInTheDocument();
    const firstRow = within(screen.getByRole("table", { name: "Open cases" })).getAllByRole("row")[1];
    expect(within(firstRow).getAllByRole("cell").map((c) => c.getAttribute("data-label"))).toEqual(["Student", "Support type", "Stage", "Since", "Provider", "Actions"]);
  });

  it("opens the edit form with focus on its heading, and Escape closes it", async () => {
    render(<SchoolFundingRecordsPanel records={[OPEN]} students={STUDENTS} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit education loan case for Asha" }));
    const heading = await screen.findByRole("heading", { name: "Update Asha's education loan case" });
    await vi.waitFor(() => expect(heading).toHaveFocus());
    fireEvent.keyDown(heading, { key: "Escape" });
    expect(screen.queryByRole("heading", { name: "Update Asha's education loan case" })).not.toBeInTheDocument();
  });

  // Final review I1/I2: the edit form unmounts on save, so the panel itself must announce the result and place focus; a case that
  // became final leaves the open table, so focus cannot go back to its (removed) Edit button.
  it("after closing a case, announces the save and moves focus to the Open cases heading", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ...OPEN, status: "closed", closure_reason: "Withdrawn" }) }));
    render(<SchoolFundingRecordsPanel records={[OPEN]} students={STUDENTS} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit education loan case for Asha" }));
    const card = within(screen.getByRole("heading", { name: "Update Asha's education loan case" }).closest(".action-card") as HTMLElement);
    fireEvent.change(card.getByLabelText("Stage"), { target: { value: "closed" } });
    fireEvent.change(card.getByLabelText("Reason for closing"), { target: { value: "Withdrawn" } });
    fireEvent.click(card.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Case saved.");
    await vi.waitFor(() => expect(screen.getByRole("heading", { name: "Open cases" })).toHaveFocus());
    vi.unstubAllGlobals();
  });

  it("after advancing a case, announces the save and returns focus to its Edit button", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ...OPEN, status: "application" }) }));
    render(<SchoolFundingRecordsPanel records={[OPEN]} students={STUDENTS} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit education loan case for Asha" }));
    const card = within(screen.getByRole("heading", { name: "Update Asha's education loan case" }).closest(".action-card") as HTMLElement);
    fireEvent.change(card.getByLabelText("Stage"), { target: { value: "application" } });
    fireEvent.click(card.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Case saved.");
    await vi.waitFor(() => expect(screen.getByRole("button", { name: "Edit education loan case for Asha" })).toHaveFocus());
    vi.unstubAllGlobals();
  });

  it("names the next action when there are no cases yet", () => {
    render(<SchoolFundingRecordsPanel records={[]} students={STUDENTS} />);
    expect(screen.getByText("No funding support cases yet. Add one below when a student needs a loan, scholarship or funding guidance.")).toBeInTheDocument();
    expect(screen.queryByText(/Finished cases/)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Add a case" })).toBeInTheDocument();
  });

  it("explains an empty portfolio instead of showing a form that cannot be used", () => {
    render(<SchoolFundingRecordsPanel records={[]} students={[]} />);
    expect(screen.getByText("No students in your portfolio yet. Contact your Overseas Admin.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add case" })).not.toBeInTheDocument();
  });
});

describe("counsellor funding page chrome", () => {
  it("adds Funding to the counsellor's navigation", () => {
    expect(SCHOOL_NAV["career-counselor"].map((item) => item.href)).toContain("/school/career-counselor/funding");
    expect(SCHOOL_NAV["career-counselor"].find((item) => item.href.endsWith("/funding"))?.label).toBe("Funding");
  });

  it("keeps the portal navigation while loading", () => {
    render(<Loading />);
    expect(screen.getAllByRole("link", { name: "Funding" }).length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Loading funding support cases")).toHaveAttribute("aria-busy", "true");
  });
});
