import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateDetail from "@/components/RecruiterCandidateDetail";
import RecruiterCandidateForm from "@/components/RecruiterCandidateForm";
import { EMPTY_FORM, candidateBody, displayValue, formFromDetail, type CandidateDetail } from "@/lib/recruiterCandidates";

// hrc-010 (DEC-SCOPE-381): the §5 profile sections of the candidate form, the body they send, and the detail's rows and completeness.
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }), usePathname: () => "/", useSearchParams: () => new URLSearchParams() }));
vi.mock("@/components/RecruiterCandidateSkills", () => ({ default: () => null }));
vi.mock("@/components/RecruiterCandidateJourney", () => ({ default: () => null }));
vi.mock("@/components/RecruiterCandidateTraining", () => ({ default: () => null }));
vi.mock("@/components/RecruiterCandidateDocuments", () => ({ default: () => null }));
vi.mock("@/components/RecruiterCandidateApplications", () => ({ default: () => null }));
vi.mock("@/components/RecruiterCalls", () => ({ default: () => null }));
vi.mock("@/components/RecruiterMessages", () => ({ default: () => null }));
vi.mock("@/components/RecruiterTimeline", () => ({ default: () => null }));
vi.mock("@/components/RecruiterRecordHistory", () => ({ default: () => null }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const sources = { items: [{ id: "s1", name: "Referral", active: true, sort_order: 1 }], total: 1, limit: 100, offset: 0 };
const candidate = {
  id: "C1", candidate_code: "CAN-000001", name: "Asha Rao", location: "Hyderabad, Telangana, India", experience_months: 36, preferred_role: "Java Developer",
  source: { id: "s1", name: "Referral", active: true }, source_detail: null, status: "available", archived: false, created_at: "2026-11-01T00:00:00Z",
  mobile: "9876543210", email: "asha@example.com", qualification: "B.Tech", college: "JNTU", passing_year: 2018, current_company: "TCS",
  notice_days: null, preferred_locations: ["Pune"], linkedin: null, archived_at: null, created_by: null, updated_by: null, updated_at: "2026-11-02T00:00:00Z",
  resumes: [], can_edit: true, country: "India", state: "Telangana", city: "Hyderabad", preferred_contact: "whatsapp", email_verified_at: null,
  relevant_experience_months: 18, tools: ["Git"], languages: ["English", "Telugu"], preferred_roles: ["Java Developer", "Backend Engineer"],
  work_modes: ["remote"], employment_types: ["full_time"], shifts: [], available_from: null, willing_to_relocate: true,
  education: [{ degree: "B.Tech", specialisation: "CSE", institution: "JNTU", year: 2018, grade: null }],
  employment: [{ employer: "Infosys", designation: "Developer", industry: null, employment_type: "full_time", start_date: "2019-01-01", end_date: "2019-12-31" },
               { employer: "TCS", designation: null, industry: null, employment_type: null, start_date: "2020-01-01", end_date: null }],
  certifications: [], is_fresher: false,
  completeness: { percent: 55, items: [
    { key: "contact_verified", label: "Contact verified", weight: 10, met: false }, { key: "education", label: "Education added", weight: 15, met: true },
    { key: "skills", label: "At least 3 skills", weight: 15, met: false }, { key: "experience", label: "Experience or fresher recorded", weight: 15, met: true },
    { key: "preferences", label: "Preferred role and location", weight: 15, met: true }, { key: "resume", label: "Resume uploaded", weight: 20, met: false },
    { key: "compensation", label: "Expected salary provided", weight: 10, met: true },
  ] },
} as unknown as CandidateDetail;

let fetchMock: ReturnType<typeof vi.fn>;
const sent = (method: string) => fetchMock.mock.calls.filter(([, init]) => init?.method === method);

beforeEach(() => {
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.startsWith("/api/v1/recruiter/catalogue/candidate-sources")) return Promise.resolve(res(sources));
    if (init?.method === "PATCH" || init?.method === "POST") return Promise.resolve(res({ ...candidate }));
    return Promise.resolve(res({ items: [] }));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("hrc-010 profile form mapping", () => {
  it("sends the rows as objects, blanks as null, a year as a number, and drops an empty row", () => {
    const form = { ...EMPTY_FORM, education: JSON.stringify([{ degree: " MCA ", specialisation: "", institution: "OU", year: "2020", grade: "" }, { degree: "", year: "" }]) };
    expect(candidateBody(form, "create").education).toEqual([{ degree: "MCA", specialisation: null, institution: "OU", year: 2020, grade: null }]);
    expect(candidateBody(EMPTY_FORM, "create")).not.toHaveProperty("education"); // create sends only what is filled
    expect(candidateBody(EMPTY_FORM, "edit").education).toEqual([]); // edit clears
  });

  it("does not send the fields the rows decide (P4/P5), and sends enum sets as lists", () => {
    const form = { ...formFromDetail(candidate), experience_months: "5" };
    const body = candidateBody(form, "edit");
    expect(body).not.toHaveProperty("experience_months"); // worked out from the jobs
    expect(body).not.toHaveProperty("current_company");
    expect(body).not.toHaveProperty("location"); // from city, state and country
    expect(body).not.toHaveProperty("qualification");
    expect(body).toMatchObject({ work_modes: ["remote"], shifts: [], preferred_roles: ["Java Developer", "Backend Engineer"], willing_to_relocate: true,
      relevant_experience_months: 18, languages: ["English", "Telugu"] });
    const legacy = candidateBody({ ...EMPTY_FORM, experience_months: "0", location: "Pune" }, "edit");
    expect(legacy).toMatchObject({ experience_months: 0, location: "Pune" }); // no rows, no structured place: the manual values go
  });

  it("shows a row set and an enum set as text in the stale-record notice", () => {
    expect(displayValue("employment", formFromDetail(candidate).employment)).toBe("Infosys · Developer · Full time · 2019-01-01 · 2019-12-31; TCS · 2020-01-01");
    expect(displayValue("work_modes", "onsite,remote")).toBe("On-site, Remote");
    expect(displayValue("city", "Pune")).toBe("Pune");
  });
});

describe("hrc-010 candidate form", () => {
  it("adds an employment row and a degree, hides the manual experience, and sends them", async () => {
    const empty = { ...candidate, education: [], employment: [], experience_months: null, current_company: null } as CandidateDetail;
    render(<RecruiterCandidateForm initial={empty} onSaved={vi.fn()} />);
    expect(screen.getByLabelText("Total experience (months)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "+ Add employment" }));
    const job = screen.getByRole("group", { name: "Employment history 1" });
    fireEvent.change(within(job).getByLabelText("Employer *"), { target: { value: "Wipro" } });
    fireEvent.change(within(job).getByLabelText("Start date *"), { target: { value: "2021-01-01" } });
    expect(screen.queryByLabelText("Total experience (months)")).not.toBeInTheDocument(); // P4: derived now
    fireEvent.click(screen.getByRole("button", { name: "+ Add education" }));
    fireEvent.change(within(screen.getByRole("group", { name: "Education 1" })).getByLabelText("Degree"), { target: { value: "B.Sc" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Hybrid" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(sent("PATCH")).toHaveLength(1));
    const body = JSON.parse(String(sent("PATCH")[0][1].body));
    expect(body.employment).toEqual([{ employer: "Wipro", designation: null, industry: null, employment_type: null, start_date: "2021-01-01", end_date: null }]);
    expect(body.education[0]).toMatchObject({ degree: "B.Sc" });
    expect(body.work_modes).toEqual(["hybrid", "remote"]);
    expect(body).not.toHaveProperty("experience_months");
  });

  it("removes a row by its named button", () => {
    render(<RecruiterCandidateForm initial={candidate} onSaved={vi.fn()} />);
    expect(screen.getAllByRole("group", { name: /^Employment history \d$/ })).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Remove employment 1" }));
    expect(screen.getAllByRole("group", { name: /^Employment history \d$/ })).toHaveLength(1);
    expect(within(screen.getByRole("group", { name: "Employment history 1" })).getByLabelText("Employer *")).toHaveValue("TCS");
  });
});

describe("hrc-010 legacy education (QA-02: rec-012's resume apply and old clients set the single fields)", () => {
  const legacy = { ...candidate, education: [], qualification: "B.Tech", college: "JNTU", passing_year: 2018 } as CandidateDetail;

  it("shows the legacy qualification as the education line while there are no rows", () => {
    render(<RecruiterCandidateDetail initial={legacy} />);
    expect(screen.getByText("B.Tech · JNTU · 2018")).toBeInTheDocument();
  });

  it("pre-fills education row 1 from them in the edit form, so a save makes it a row", () => {
    expect(JSON.parse(formFromDetail(legacy).education)).toEqual([{ degree: "B.Tech", specialisation: "", institution: "JNTU", year: "2018", grade: "" }]);
    expect(JSON.parse(formFromDetail({ ...legacy, qualification: null, college: null, passing_year: null } as CandidateDetail).education)).toEqual([]);
  });
});

describe("hrc-010 candidate detail", () => {
  it("shows the completeness meter, what is missing, the rows and the preferences", () => {
    render(<RecruiterCandidateDetail initial={candidate} />);
    const meter = screen.getByRole("meter", { name: "Profile 55% complete" });
    expect(meter).toHaveAttribute("aria-valuenow", "55");
    expect(screen.getByText(/Missing: Contact verified \(10%\), At least 3 skills \(15%\), Resume uploaded \(20%\)/)).toBeInTheDocument();
    expect(screen.getByText("B.Tech · CSE · JNTU · 2018")).toBeInTheDocument();
    expect(screen.getByText(/TCS · 2020-01-01/)).toBeInTheDocument();
    expect(screen.getByText("Current")).toBeInTheDocument();
    expect(screen.getByText("(from employment history)")).toBeInTheDocument();
    expect(screen.getByText("Java Developer, Backend Engineer")).toBeInTheDocument();
    expect(screen.getByText("WhatsApp")).toBeInTheDocument();
    expect(screen.getByText("Remote")).toBeInTheDocument();
  });
});
