import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStudentProfileCard from "@/components/AgentStudentProfileCard";
import DataTable from "@/components/DataTable";
import StudentProfileForm from "@/components/StudentProfileForm";
import { fieldPlace, type StudentProfile } from "@/lib/studentProfile";

const URL = "/api/v1/counselor/students/s1/profile";
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const COUNTRIES = [{ id: "c1", name: "United Kingdom" }, { id: "c2", name: "Germany" }];
const profile = (extra: Partial<StudentProfile> = {}): StudentProfile => ({
  exists: true, date_of_birth: "2003-05-14", nationality: "Indian", city: "Hyderabad", state: "Telangana", passport_number: "Z1234567",
  passport_expiry: "2031-01-31", work_experience_months: null, work_experience_details: null, preferred_countries: [{ id: "c1", name: "United Kingdom" }],
  preferred_course: "MSc CS", preferred_level: "PG", preferred_intake: "Sep 2027", study_mode: "full_time", budget_min: null, budget_max: null,
  budget_currency: null, updated_at: "2026-10-24T10:00:00Z", updated_by_name: "Nora Counselor",
  qualifications: [{ level: "bachelor", qualification_name: "B.Tech", institution: "JNTU", board_university: null, year_completed: 2024, score_type: "cgpa", score: "8.20", backlogs: 0 }],
  english_tests: [{ test_type: "IELTS", status: "taken", overall_score: "7.5", test_date: "2025-11-02", valid_until: "2023-11-02", remarks: null, expired: true }],
  ...extra,
});
const saved = (p: StudentProfile) => ({ student: { id: "s1", full_name: "Asha Rao", student_code: null }, profile: p });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("StudentProfileForm (ccrm-007)", () => {
  it("shows the saved profile, who saved it last and an expired test", () => {
    render(<StudentProfileForm initial={profile()} url={URL} countries={COUNTRIES} />);
    expect(screen.getByLabelText("Nationality")).toHaveValue("Indian");
    expect(screen.getByLabelText("Passport number")).toHaveValue("Z1234567");
    expect(screen.getByRole("listitem", { name: "United Kingdom" })).toBeInTheDocument();
    expect(screen.getByLabelText("Qualification 1 level")).toHaveValue("bachelor");
    expect(screen.getByText("Expired")).toBeInTheDocument();
    expect(screen.getByText(/Last saved by Nora Counselor/)).toBeInTheDocument();
  });

  it("says when nothing has been saved yet", () => {
    render(<StudentProfileForm initial={profile({ exists: false, qualifications: [], english_tests: [], preferred_countries: [], updated_by_name: null, updated_at: null })} url={URL} countries={COUNTRIES} />);
    expect(screen.getByText("No profile saved yet.")).toBeInTheDocument();
    expect(screen.getByText("No qualifications added.")).toBeInTheDocument();
    expect(screen.getByText("No English tests added.")).toBeInTheDocument();
  });

  it("adds a qualification and a country, then saves the whole profile", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res(saved(profile())));
    vi.stubGlobal("fetch", fetchMock);
    render(<StudentProfileForm initial={profile()} url={URL} countries={COUNTRIES} />);
    fireEvent.click(screen.getByRole("button", { name: "Add qualification" }));
    fireEvent.change(screen.getByLabelText("Qualification 2 level"), { target: { value: "class_12" } });
    fireEvent.change(screen.getByLabelText("Qualification 2 institution"), { target: { value: "Narayana" } });
    fireEvent.change(screen.getByLabelText("Add a preferred country"), { target: { value: "c2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByText("Profile saved.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(URL);
    expect(init.method).toBe("PUT");
    const body = JSON.parse(init.body);
    expect(body.preferred_country_ids).toEqual(["c1", "c2"]);
    expect(body.qualifications.map((q: { level: string }) => q.level)).toEqual(["bachelor", "class_12"]);
    expect(body.qualifications[1].institution).toBe("Narayana");
    expect(body.english_tests[0]).toEqual({ test_type: "IELTS", status: "taken", overall_score: "7.5", test_date: "2025-11-02", valid_until: "2023-11-02", remarks: null });
  });

  it("removes a row and a country", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res(saved(profile())));
    vi.stubGlobal("fetch", fetchMock);
    render(<StudentProfileForm initial={profile()} url={URL} countries={COUNTRIES} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove English test 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove United Kingdom" }));
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));
    await screen.findByText("Profile saved.");
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.english_tests).toEqual([]);
    expect(body.preferred_country_ids).toEqual([]);
  });

  it("keeps the entries and says where the problem is when the server refuses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: [{ loc: ["body", "qualifications", 0, "score"], msg: "Value error, A cgpa score must be between 0 and 10" }] }, 422)));
    render(<StudentProfileForm initial={profile()} url={URL} countries={COUNTRIES} />);
    fireEvent.change(screen.getByLabelText("City"), { target: { value: "Pune" } });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByText("Qualification 1 · Score: A cgpa score must be between 0 and 10")).toBeInTheDocument();
    expect(screen.getByLabelText("City")).toHaveValue("Pune");
  });

  it("ignores a second save while one is in flight", async () => {
    let resolve: (r: Response) => void = () => {};
    const fetchMock = vi.fn().mockReturnValue(new Promise<Response>((r) => (resolve = r)));
    vi.stubGlobal("fetch", fetchMock);
    render(<StudentProfileForm initial={profile()} url={URL} countries={COUNTRIES} />);
    const save = screen.getByRole("button", { name: "Save profile" });
    fireEvent.click(save);
    fireEvent.click(save);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    resolve(res(saved(profile())));
    expect(await screen.findByText("Profile saved.")).toBeInTheDocument();
  });

  it("caps qualifications and English tests", () => {
    render(<StudentProfileForm initial={profile({ english_tests: Array(5).fill(profile().english_tests[0]) })} url={URL} countries={COUNTRIES} />);
    expect(screen.queryByRole("button", { name: "Add English test" })).not.toBeInTheDocument();
    expect(screen.getByText("Up to 5 English tests.")).toBeInTheDocument();
  });
});

describe("fieldPlace", () => {
  it("words a 422 location", () => {
    expect(fieldPlace(["body", "english_tests", 1, "overall_score"])).toBe("English test 2 · Overall score");
    expect(fieldPlace(["body", "budget_min"])).toBe("Budget from");
    expect(fieldPlace(["body"])).toBeNull();
  });
});

describe("AgentStudentProfileCard (ccrm-007 P2/P3)", () => {
  it("shows the profile read-only, without a passport", async () => {
    const p = profile();
    delete p.passport_number;
    delete p.passport_expiry;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ profile: p })));
    render(<AgentStudentProfileCard studentId="as1" />);
    const card = await screen.findByRole("region", { name: "Student profile" });
    expect(within(card).getByText("Bachelor's degree — B.Tech, JNTU, 2024, CGPA 8.20")).toBeInTheDocument();
    expect(within(card).getByText("IELTS 7.5 · Taken · expired")).toBeInTheDocument();
    expect(within(card).queryByText(/passport/i)).not.toBeInTheDocument();
    expect(within(card).queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("says when the student has not filled a profile, and when it cannot be loaded", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ profile: profile({ exists: false, qualifications: [], english_tests: [], preferred_countries: [] }) })));
    render(<AgentStudentProfileCard studentId="as1" />);
    expect(await screen.findByText("The student's profile has not been filled in yet.")).toBeInTheDocument();
    cleanup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "x" }, 500)));
    render(<AgentStudentProfileCard studentId="as1" />);
    expect(await screen.findByText("The student's profile could not be loaded.")).toBeInTheDocument();
  });
});

describe("DataTable student_profile cell (ccrm-007)", () => {
  it("links to the profile page, and shows nothing without a link", () => {
    render(
      <DataTable
        columns={[{ key: "student", label: "Student" }, { key: "profile", label: "", type: "student_profile" }]}
        rows={[{ id: "1", student: "Asha Rao", profile: "/overseas/counselor/students/s1/profile" }, { id: "2", student: "No Login", profile: null }]}
        label="Students"
      />,
    );
    const link = screen.getByRole("link", { name: "Profile for Asha Rao" });
    expect(link).toHaveAttribute("href", "/overseas/counselor/students/s1/profile");
    expect(screen.queryByRole("link", { name: "Profile for No Login" })).not.toBeInTheDocument();
  });
});

describe("StudentProfileForm intake (ccrm-047)", () => {
  it("sets the intake with the month + year picker", async () => {
    const year = String(new Date().getFullYear() + 2);
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => Promise.resolve(res(saved({ ...profile(), ...JSON.parse(String(init?.body)) }))));
    vi.stubGlobal("fetch", fetchMock);
    render(<StudentProfileForm initial={profile()} url={URL} countries={COUNTRIES} section="preferences" />);
    expect(screen.getByLabelText("Intake month")).toHaveValue("Sep");
    fireEvent.change(screen.getByLabelText("Intake month"), { target: { value: "Feb" } });
    fireEvent.change(screen.getByLabelText("Intake year"), { target: { value: year } });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));
    await screen.findByText("Profile saved.");
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]!.body)).preferred_intake).toBe(`Feb ${year}`);
  });

  it("keeps a legacy intake and refuses a half-chosen one without saving", async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => Promise.resolve(res(saved({ ...profile(), ...JSON.parse(String(init?.body)) }))));
    vi.stubGlobal("fetch", fetchMock);
    render(<StudentProfileForm initial={profile({ preferred_intake: "September 2027" })} url={URL} countries={COUNTRIES} section="preferences" />);
    expect(screen.getByText(/Saved as “September 2027”/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Intake month"), { target: { value: "Oct" } });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByText("Choose both the month and the year for the intake.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
