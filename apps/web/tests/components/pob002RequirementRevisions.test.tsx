import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterRequirementDetail from "@/components/RecruiterRequirementDetail";
import RecruiterRequirementForm from "@/components/RecruiterRequirementForm";
import RequirementRevisions from "@/components/RequirementRevisions";
import { actionLabel, humanise } from "@/lib/recruiterHistory";
import type { CommercialTerms, Requirement } from "@/lib/recruiterRequirements";
import { requirementBody, revisionText, stepList, valuesOf, wire } from "@/lib/recruiterRequirements";

// pob-002 (DEC-SCOPE-405): revisions (R5), the hiring process (R6), the per-requirement terms (R7/R8) and the backup owner (R9). The
// server decides every rule; these check what is shown, what is sent and how a failure reads.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn(), replace: vi.fn() }), usePathname: () => "/x" }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const PERMS = { can_edit: true, can_change_status: false, can_reassign: false, can_view_matches: false, can_manage_owners: true, can_view_candidates: false };
const TERMS: CommercialTerms = {
  fee: { basis: "fixed", value: "50000.00", inherited: true }, payment_trigger: "days_after_joining", payment_trigger_label: "Days after joining",
  payment_days: 45, payment_terms: { value: "30 days from invoice", inherited: true }, replacement_terms: { value: "Replace within 90 days", inherited: false },
  can_edit: true,
};
const requirement = (over: Partial<Requirement> = {}) =>
  ({
    id: "R1", code: "REQ-0001", title: "Java Dev", company: { id: "CO1", code: "CO-1", name: "Acme" }, location: "Pune", status: "sourcing", status_label: "Sourcing",
    phase: "open", phase_label: "Open", source: "recruiter", priority: null, vacancies: 2, closes_on: null, requirement_date: null, deadline_state: null,
    assigned_recruiter: { id: "U1", full_name: "Rita Recruiter", active: true }, permissions: PERMS, description: "", department: null, job_category: null, qualification: null,
    experience_min_months: null, experience_max_months: null, salary_min: null, salary_max: null, work_mode: null, shift: null, employment_type: null,
    joining_requirement: null, skills: [], joined_count: 0, allowed_statuses: [], status_history: [], created_by: null, created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-04T04:00:00Z", approval: { required: false, submitted_by: null, submitted_at: null, can_submit: false, can_decide: false },
    owners: [], visibility: { key: "public", label: "Public website", segment_pool: null, can_change: false },
    backup_owner: { id: "B1", full_name: "Bala Backup", active: true }, interview_rounds: ["Technical", "HR"], screening_steps: [],
    decision_maker: { id: "D1", name: "Dev Decider", designation: "VP", active: true }, expected_tat_days: 21, commercial_terms: TERMS, ...over,
  }) as Requirement;
const PAGE = {
  items: [
    { revision: 2, author: { id: "U1", full_name: "Rita Recruiter" }, reason: "Client added a seat", created_at: "2026-11-05T05:00:00Z",
      changed_fields: [{ field: "vacancies", label: "Number of vacancies" }] },
    { revision: 1, author: { id: "U1", full_name: "Rita Recruiter" }, reason: null, created_at: "2026-11-05T04:00:00Z", changed_fields: [] },
  ],
  total: 2, limit: 100, offset: 0,
};
const DETAIL = {
  revision: 2, author: { id: "U1", full_name: "Rita Recruiter" }, reason: "Client added a seat", created_at: "2026-11-05T05:00:00Z", compared_to: 1,
  values: [{ field: "vacancies", label: "Number of vacancies", value: 3 }, { field: "relocation_required", label: "Relocation required", value: true }],
  changes: [{ field: "vacancies", label: "Number of vacancies", before: 2, after: 3 }],
};

let gets: string[];
let routes: (url: string) => Response | undefined;

beforeEach(() => {
  gets = [];
  routes = () => undefined;
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    gets.push(url);
    return Promise.resolve(routes(url) ?? res({ items: [], total: 0, versions: [] }));
  }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("pob-002 helpers", () => {
  it("sends rounds one per line, blank lines dropped, and an empty list as null", () => {
    expect(stepList("Technical\n\n  HR \n")).toEqual(["Technical", "HR"]);
    expect(wire("interview_rounds", "  \n")).toBeNull();
    expect(wire("expected_tat_days", "21")).toBe(21);
  });

  it("edits the requirement's own terms only: a term from the contract opens blank", () => {
    const values = valuesOf(requirement());
    expect(values.payment_terms).toBe("");
    expect(values.replacement_terms).toBe("Replace within 90 days");
    expect(values.interview_rounds).toBe("Technical\nHR");
    expect(requirementBody({ ...values, expected_tat_days: "30" }, values)).toEqual({ expected_tat_days: 30 });
  });

  it("QA-01: the Change history names the new fields in words", () => {
    expect(humanise("expected_tat_days")).toBe("Expected turnaround (days)");
    expect(humanise("decision_maker_contact")).toBe("Decision-maker");
    expect(humanise("payment_days")).toBe("Payment due (days after joining)");
    expect(actionLabel("recruiter_requirement.backup_released")).toBe("Backup owner removed (user deactivated)");
    expect(humanise("salary_min")).toBe("Salary min"); // unchanged for everything else
  });

  it("reads stored values as words", () => {
    expect(revisionText(null)).toBe("—");
    expect(revisionText(true)).toBe("Yes");
    expect(revisionText("days_after_joining")).toBe("Days after joining");
    expect(revisionText("onsite")).toBe("On-site");
  });
});

describe("pob-002 revisions section", () => {
  it("lists the revisions and shows a revision's changes against the one before it", async () => {
    routes = (url) => (url.endsWith("/revisions?limit=100") ? res(PAGE) : url.includes("/revisions/2") ? res(DETAIL) : undefined);
    render(<RequirementRevisions requirementId="R1" />);
    const list = await screen.findByRole("list", { name: "Revisions" });
    expect(within(list).getByText("Reason: Client added a seat")).toBeTruthy();
    expect(within(list).getByText("Changed: Number of vacancies")).toBeTruthy();
    expect(within(list).getByText("The requirement as first recorded")).toBeTruthy();
    const view = screen.getByRole("button", { name: "View revision 2" });
    fireEvent.click(view);
    expect(view.getAttribute("aria-expanded")).toBe("true");
    const changes = await screen.findByRole("list", { name: "Changes from revision 1" });
    expect(changes.textContent).toBe("Number of vacancies: 2 → 3");
    expect(gets).toContain("/api/v1/recruiter/requirements/R1/revisions/2?compare_to=1");
    expect(screen.getByText("Yes")).toBeTruthy();
  });

  it("shows an error with a retry when the list cannot be read", async () => {
    let fail = true;
    routes = (url) => (url.endsWith("/revisions?limit=100") ? (fail ? res({ detail: "x" }, 500) : res(PAGE)) : undefined);
    render(<RequirementRevisions requirementId="R1" />);
    expect((await screen.findByRole("alert")).textContent).toBe("Unable to load the revisions.");
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("list", { name: "Revisions" })).toBeTruthy();
  });

  it("says so when there are none yet", async () => {
    render(<RequirementRevisions requirementId="R1" />);
    expect(await screen.findByText(/No revisions yet/)).toBeTruthy();
  });
});

describe("pob-002 detail and form", () => {
  it("shows the hiring process, the backup owner and the terms with their source", async () => {
    render(<RecruiterRequirementDetail initial={requirement()} initialJd={null} />);
    const details = screen.getByRole("region", { name: "Details" });
    expect(within(details).getByText("Bala Backup")).toBeTruthy();
    expect(within(details).getByText("Dev Decider, VP")).toBeTruthy();
    expect(within(details).getByText("21 days")).toBeTruthy();
    const terms = screen.getByRole("region", { name: "Commercial terms" });
    expect(within(terms).getByText("Days after joining (45 days)")).toBeTruthy();
    expect(within(terms).getAllByText("From the contract")).toHaveLength(2); // the fee and the payment terms, not the replacement terms
    await waitFor(() => expect(gets.some((u) => u.endsWith("/revisions?limit=100"))).toBe(true));
  });

  it("has no terms card and no terms section without the grant", () => {
    const { unmount } = render(<RecruiterRequirementDetail initial={requirement({ commercial_terms: undefined })} initialJd={null} />);
    expect(screen.queryByRole("region", { name: "Commercial terms" })).toBeNull();
    unmount();
    render(<RecruiterRequirementForm mode="edit" requirement={requirement({ commercial_terms: undefined })} onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole("group", { name: "Hiring process" })).toBeTruthy();
    expect(screen.queryByRole("group", { name: "Commercial terms" })).toBeNull();
  });

  it("shows the terms and the backup owner only to those who may change them", () => {
    const { unmount } = render(<RecruiterRequirementForm mode="edit" requirement={requirement()} onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole("group", { name: "Commercial terms" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "Backup owner" })).toBeTruthy();
    expect(screen.getByLabelText("Payment due (days after joining)")).toBeTruthy();
    expect(screen.getByText(`Leave empty to use the contract's: "30 days from invoice"`)).toBeTruthy();
    unmount();
    render(<RecruiterRequirementForm mode="edit" requirement={requirement({ permissions: { ...PERMS, can_manage_owners: false }, commercial_terms: { ...TERMS, can_edit: false } })}
      onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByRole("group", { name: "Commercial terms" })).toBeNull();
    expect(screen.queryByRole("group", { name: "Backup owner" })).toBeNull();
  });
});
