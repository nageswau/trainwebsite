import { describe, expect, it } from "vitest";

import { collegeText, type Drive, driveBody, EMPTY_DRIVE, formOf, formProblem, funnelSteps } from "@/lib/recruiterDrives";

// rec-029 (DEC-SCOPE-175): the drive form <-> body mapping (a PATCH sends only what changed), the client-side form checks (AC2 too), the
// college line and the funnel steps (Appendix B C2-C7).
const drive = (over: Partial<Drive> = {}): Drive => ({
  id: "d1", code: "DRV-000001", status: "planned", status_label: "Planned", drive_date: "2026-11-20", job_role: "Graduate Engineer Trainee",
  vacancies: 40, eligibility: null, students_registered: 200, students_attended: 100, company: { id: "c1", code: "CMP-000001", name: "XYZ Technologies" },
  college: { org_id: null, code: null, name: "ABC College", city: null }, can_edit: true, created_at: "2026-10-11T00:00:00Z", updated_at: "2026-10-11T00:00:00Z",
  funnel: { registered: 200, attended: 100, tagged: 40, shortlisted: 35, interviewed: 25, selected: 12, joined: 10 },
  requirements: [{ id: "j1", code: "REQ-000001", title: "GET", status: "sourcing", open: true }], statuses: [], ...over,
});

describe("drive form", () => {
  it("builds the create body from a typed college", () => {
    const form = {
      ...EMPTY_DRIVE, company: { id: "c1", label: "XYZ" }, requirements: [{ id: "j1", label: "GET" }, { id: "j2", label: "SDE" }],
      collegeName: "  ABC   College ", drive_date: "2026-11-20", job_role: " GET ", vacancies: "40", registered: "200", attended: "100",
    };
    expect(formProblem(form)).toBeNull();
    expect(driveBody(form)).toEqual({
      company_id: "c1", requirement_ids: ["j1", "j2"], college_org_id: null, college_name: "ABC College", drive_date: "2026-11-20",
      job_role: "GET", vacancies: 40, eligibility: null, students_registered: 200, students_attended: 100,
    });
  });

  it("sends the picked BDM college, not the typed name", () => {
    const form = { ...EMPTY_DRIVE, typed: false, college: { id: "o1", label: "ABC College" }, collegeName: "left over" };
    expect(driveBody(form)).toMatchObject({ college_org_id: "o1", college_name: null });
  });

  it("names the first problem, attended above registered included (AC2)", () => {
    const ok = { ...EMPTY_DRIVE, company: { id: "c1", label: "X" }, requirements: [{ id: "j1", label: "R" }], collegeName: "ABC", drive_date: "2026-11-20", job_role: "GET", vacancies: "4" };
    expect(formProblem({ ...ok, company: null })).toBe("Choose the company.");
    expect(formProblem({ ...ok, requirements: [] })).toBe("Add at least one job requirement.");
    expect(formProblem({ ...ok, collegeName: " " })).toBe("Type the college name.");
    expect(formProblem({ ...ok, typed: false })).toBe("Choose the college.");
    expect(formProblem({ ...ok, vacancies: "0" })).toBe("Vacancies must be a whole number from 1.");
    expect(formProblem({ ...ok, registered: "2.5" })).toBe("Students registered and attended must be whole numbers.");
    expect(formProblem({ ...ok, registered: "10", attended: "11" })).toBe("Students attended cannot be more than students registered.");
    expect(formProblem(ok)).toBeNull();
  });

  it("round-trips a drive and sends only the changed fields on edit", () => {
    const original = formOf(drive());
    expect(original).toMatchObject({ typed: true, collegeName: "ABC College", vacancies: "40", registered: "200", attended: "100", status: "planned" });
    expect(driveBody(original, original)).toEqual({});
    expect(driveBody({ ...original, attended: "150", status: "completed" }, original)).toEqual({ students_attended: 150, status: "completed" });
    expect(driveBody({ ...original, requirements: [] }, original)).toEqual({ requirement_ids: [] });
    expect(driveBody({ ...original, collegeName: "XYZ College" }, original)).toEqual({ college_org_id: null, college_name: "XYZ College" });
    const picked = formOf(drive({ college: { org_id: "o1", code: "ORG-000001", name: "ABC College", city: "Kochi" } }));
    expect(picked).toMatchObject({ typed: false, college: { id: "o1", label: "ABC College", detail: "ORG-000001 · Kochi" } });
  });
});

describe("drive display", () => {
  it("reads the college with its city when known", () => {
    expect(collegeText(drive().college)).toBe("ABC College");
    expect(collegeText({ org_id: "o1", code: "ORG-1", name: "ABC College", city: "Kochi" })).toBe("ABC College, Kochi");
  });

  it("lists the funnel in the source order", () => {
    expect(funnelSteps(drive().funnel)).toEqual([
      ["Registered", 200], ["Attended", 100], ["Shortlisted", 35], ["Interviewed", 25], ["Selected", 12], ["Joined", 10],
    ]);
  });
});
