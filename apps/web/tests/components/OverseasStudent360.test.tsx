import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CounselorWalkInStudentRow from "@/components/CounselorWalkInStudentRow";
import DataTable from "@/components/DataTable";
import StudentDocumentDownload from "@/components/StudentDocumentDownload";
import StudentProfileForm from "@/components/StudentProfileForm";
import { studentTab } from "@/lib/overseasStudent360";
import type { StudentProfile } from "@/lib/studentProfile";

const URL = "/api/v1/counselor/students/s1/profile";
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const profile: StudentProfile = {
  exists: true, date_of_birth: "2003-05-14", nationality: "Indian", city: null, state: null, passport_number: null, passport_expiry: null,
  work_experience_months: 12, work_experience_details: null, preferred_countries: [{ id: "c1", name: "United Kingdom" }], preferred_course: "MSc CS",
  preferred_level: "PG", preferred_intake: null, study_mode: null, budget_min: null, budget_max: null, budget_currency: null, updated_at: null, updated_by_name: null,
  qualifications: [{ level: "bachelor", qualification_name: "B.Tech", institution: "JNTU", board_university: null, year_completed: 2024, score_type: "cgpa", score: "8.20", backlogs: 0 }],
  english_tests: [{ test_type: "IELTS", status: "taken", overall_score: "7.5", test_date: "2025-11-02", valid_until: "2027-11-02", remarks: null, expired: false }],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("student 360 tabs (ccrm-009)", () => {
  it("falls back to Overview for a missing or unknown tab", () => {
    expect(studentTab(undefined)).toBe("overview");
    expect(studentTab("nope")).toBe("overview");
    expect(studentTab(["history", "x"])).toBe("history");
    expect(studentTab("english")).toBe("english");
  });
});

describe("StudentProfileForm sections (ccrm-009 V2)", () => {
  it("Academic shows personal details, academic history and work experience only", () => {
    render(<StudentProfileForm initial={profile} url={URL} countries={[]} section="academic" />);
    expect(screen.getByText("Personal details")).toBeInTheDocument();
    expect(screen.getByText("Academic history")).toBeInTheDocument();
    expect(screen.getByText("Work experience")).toBeInTheDocument();
    expect(screen.queryByText("Study preferences")).not.toBeInTheDocument();
    expect(screen.queryByText("English tests")).not.toBeInTheDocument();
  });

  it("English shows the tests only", () => {
    render(<StudentProfileForm initial={profile} url={URL} countries={[]} section="english" />);
    expect(screen.getByText("English tests")).toBeInTheDocument();
    expect(screen.queryByText("Academic history")).not.toBeInTheDocument();
  });

  it("a save on the Preferences tab still sends the qualifications and tests it does not show", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ student: { id: "s1", full_name: "Asha", student_code: null }, profile }));
    vi.stubGlobal("fetch", fetchMock);
    render(<StudentProfileForm initial={profile} url={URL} countries={[]} section="preferences" />);
    expect(screen.queryByText("Academic history")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Course or subject"), { target: { value: "MSc AI" } });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));
    await screen.findByText("Profile saved.");
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.preferred_course).toBe("MSc AI");
    expect(body.qualifications).toHaveLength(1);
    expect(body.english_tests).toHaveLength(1);
    expect(body.nationality).toBe("Indian");
  });
});

describe("Open link (ccrm-009 B5)", () => {
  it("renders the 360 link only where the server sent one", () => {
    const columns = [{ key: "student", label: "Student" }, { key: "open", label: "", type: "student_360" }];
    render(<DataTable label="Students" columns={columns} rows={[{ id: "a", student: "Asha", open: "/overseas/counselor/students/s1" }, { id: "b", student: "No login", open: null }]} />);
    const links = screen.getAllByRole("link", { name: /Open/ });
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "/overseas/counselor/students/s1");
    expect(links[0]).toHaveAccessibleName("Open Asha");
  });
});

describe("walk-in student row (ccrm-009 B5)", () => {
  it("links the linked student to their 360", () => {
    const student = { id: "s1", full_name: "Meena Walkin", email: "meena@example.local", phone: null, student_code: null, setup: null };
    render(<ul><CounselorWalkInStudentRow student={student} onChanged={vi.fn()} /></ul>);
    expect(screen.getByRole("link", { name: "Open Meena Walkin" })).toHaveAttribute("href", "/overseas/counselor/students/s1");
  });
});

describe("StudentDocumentDownload", () => {
  it("opens the short-lived link from the scoped route", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ url: "https://files.example/x", expires_in: 900 })));
    const open = vi.fn();
    vi.stubGlobal("open", open);
    render(<StudentDocumentDownload id="d1" name="Passport" />);
    fireEvent.click(screen.getByRole("button", { name: "Download Passport" }));
    await waitFor(() => expect(open).toHaveBeenCalledWith("https://files.example/x", "_blank", "noopener"));
    expect((fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBe("/api/v1/workflows/overseas/documents/d1/download");
  });

  it("shows the server's refusal", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Document is outside your assigned scope" }, 403)));
    render(<StudentDocumentDownload id="d1" name="Passport" />);
    fireEvent.click(screen.getByRole("button", { name: "Download Passport" }));
    expect(await screen.findByText("Document is outside your assigned scope")).toBeInTheDocument();
  });
});
