import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import InstitutionStudentPool, { permissionProblems } from "@/components/InstitutionStudentPool";
import RecruiterCandidateImport from "@/components/RecruiterCandidateImport";
import { applicationLabel, importPath, type Permission, type StudentPool } from "@/lib/institutionPool";

// pob-014 (DEC-SCOPE-425): the institution student pool on a college and the import wizard's institution mode.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
type Call = { url: string; init?: RequestInit };
function serve(handler: (call: Call) => Response) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const call = { url: String(url), init };
    calls.push(call);
    return Promise.resolve(handler(call));
  }));
  return calls;
}

const permission: Permission = {
  id: "p1", agreement_reference: "MoU-2026", mou_id: null, purposes: ["placement"], valid_from: "2026-11-01", expires_on: "2027-05-31", notes: null,
  status: "active", users: [{ id: "u1", full_name: "Asha Recruiter" }], student_count: 1, created_at: "2026-11-07T10:00:00Z", revoked_at: null,
};
const pool = (patch: Partial<StudentPool> = {}): StudentPool => ({
  college: { id: "o1", name: "St Mary's College" }, can_manage: false, permissions: [permission],
  students: {
    items: [{ id: "c1", candidate_code: "CAN-000101", name: "Ravi Kumar", passing_year: 2027, qualification: "B.Tech CSE", notice_status: "consented",
              permission_id: "p1", placement_status: "shortlisted" }],
    total: 1, limit: 25, offset: 0,
  },
  ...patch,
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("helpers", () => {
  it("names the placement status and builds the import link", () => {
    expect(applicationLabel(null)).toBe("Not applied");
    expect(applicationLabel("profile_shared")).toBe("Profile shared");
    expect(importPath("o1", "p1")).toBe("/recruiter/candidates/import?college=o1&permission=p1");
  });
});

describe("InstitutionStudentPool", () => {
  it("shows the permissions and the students the viewer may see, with an import link for a listed person", async () => {
    serve(() => res(pool()));
    render(<InstitutionStudentPool orgId="o1" viewerId="u1" />);
    const students = await screen.findByRole("table", { name: "Students" });
    expect(within(students).getByText("Ravi Kumar")).toBeTruthy();
    expect(within(students).getByText("Shortlisted")).toBeTruthy();
    expect(within(students).getByText("Consent given")).toBeTruthy();
    const permissions = screen.getByRole("table", { name: "Data permissions" });
    expect(within(permissions).getByText("Active")).toBeTruthy();
    expect(within(permissions).getByRole("link", { name: "Import students" }).getAttribute("href")).toBe(importPath("o1", "p1"));
    expect(screen.queryByRole("button", { name: "Add a data permission" })).toBeNull();
  });

  it("offers no import to someone the permission does not name, and says so when nothing is shown", async () => {
    serve(() => res(pool({ permissions: [], students: { items: [], total: 0, limit: 25, offset: 0 } })));
    render(<InstitutionStudentPool orgId="o1" viewerId="u9" />);
    expect(await screen.findByText("No data permission names you for this college.")).toBeTruthy();
    expect(screen.getByText("No students to show.")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Import students" })).toBeNull();
  });

  it("shows an error with a retry when the pool cannot load", async () => {
    let fail = true;
    serve(() => (fail ? res({ detail: "x" }, 500) : res(pool())));
    render(<InstitutionStudentPool orgId="o1" viewerId="u1" />);
    expect(await screen.findByText("Unable to load the student pool.")).toBeTruthy();
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("table", { name: "Students" })).toBeTruthy();
  });

  it("sends the filters", async () => {
    const calls = serve(() => res(pool()));
    render(<InstitutionStudentPool orgId="o1" viewerId="u1" />);
    await screen.findByRole("table", { name: "Students" });
    fireEvent.change(screen.getByLabelText("Pass-out year"), { target: { value: "2027" } });
    fireEvent.change(screen.getByLabelText("Course"), { target: { value: "B.Tech" } });
    fireEvent.click(screen.getByRole("button", { name: "Filter" }));
    await waitFor(() => expect(calls.at(-1)?.url).toContain("pass_out_year=2027"));
    expect(calls.at(-1)?.url).toContain("course=B.Tech");
  });

  it("lets a manager add a permission with its purposes and people", async () => {
    const calls = serve((call) => {
      if (call.url.includes("candidate-tasks/assignees")) return res([{ id: "u2", full_name: "Bina Recruiter" }]);
      if (call.init?.method === "POST") return res({ permission }, 201);
      return res(pool({ can_manage: true }));
    });
    render(<InstitutionStudentPool orgId="o1" viewerId="m1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Add a data permission" }));
    fireEvent.change(screen.getByLabelText("Agreement reference"), { target: { value: "MoU-2027" } });
    fireEvent.change(screen.getByLabelText("Valid from"), { target: { value: "2026-11-01" } });
    fireEvent.change(screen.getByLabelText("Expires on"), { target: { value: "2027-10-31" } });
    fireEvent.click(screen.getByLabelText("Internship"));
    fireEvent.click(await screen.findByLabelText("Bina Recruiter"));
    fireEvent.click(screen.getByRole("button", { name: "Add permission" }));
    await screen.findByText("Permission added.");
    const sent = calls.find((c) => c.init?.method === "POST");
    expect(sent?.url).toBe("/api/v1/recruiter/colleges/o1/data-permissions");
    expect(JSON.parse(String(sent?.init?.body))).toEqual({
      agreement_reference: "MoU-2027", valid_from: "2026-11-01", expires_on: "2027-10-31", purposes: ["placement", "internship"], notes: null, user_ids: ["u2"],
    });
  });

  it("asks before revoking and shows the server's refusal", async () => {
    const calls = serve((call) => (call.init?.method === "POST" ? res({ detail: "This permission was revoked" }, 409) : res(pool({ can_manage: true }))));
    render(<InstitutionStudentPool orgId="o1" viewerId="m1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Revoke" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, revoke" }));
    expect((await screen.findByRole("alert")).textContent).toBe("This permission was revoked");
    expect(calls.find((c) => c.init?.method === "POST")?.url).toBe("/api/v1/recruiter/colleges/o1/data-permissions/p1/revoke");
  });
});

describe("RecruiterCandidateImport institution mode", () => {
  const sources = { items: [{ id: "s1", name: "College", active: true, sort_order: 1 }], total: 1, limit: 100, offset: 0 };
  function serveImport(active = true) {
    return serve((call) => {
      if (call.url.includes("candidate-sources")) return res(sources);
      if (call.url.includes("student-pool")) return res(pool({ permissions: [{ ...permission, status: active ? "active" : "expired" }] }));
      if (call.url.includes("/preview")) return res({ total_rows: 1, new_count: 1, matched_count: 0, error_count: 0, rows: [] });
      return res({ items: [], total: 0, limit: 10, offset: 0 });
    });
  }

  it("names the college and agreement, requires the notice status and sends the permission", async () => {
    const calls = serveImport();
    render(<RecruiterCandidateImport institution={{ college: "o1", permission: "p1" }} />);
    expect(await screen.findByText("St Mary's College")).toBeTruthy();
    await waitFor(() => expect(screen.getByRole("option", { name: "College" })).toBeTruthy());
    fireEvent.change(screen.getByLabelText("Candidate source"), { target: { value: "s1" } });
    fireEvent.change(screen.getByLabelText("Basis for holding the details"), { target: { value: "consent" } });
    const file = new File(["name,mobile\nRavi,9876543210\n"], "students.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText("Filled-in candidates file"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Check file" }));
    expect((await screen.findByRole("alert")).textContent).toContain("privacy notice or gave consent");
    fireEvent.change(screen.getByLabelText("Students' notice or consent"), { target: { value: "consented" } });
    fireEvent.click(screen.getByRole("button", { name: "Check file" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/preview"))).toBe(true));
    const body = calls.find((c) => c.url.endsWith("/preview"))?.init?.body as FormData;
    expect(body.get("institution_permission_id")).toBe("p1");
    expect(body.get("notice_status")).toBe("consented");
  });

  it("says when the permission is not in force", async () => {
    serveImport(false);
    render(<RecruiterCandidateImport institution={{ college: "o1", permission: "p1" }} />);
    expect((await screen.findByText(/not in force or does not name you/)).getAttribute("role")).toBe("alert");
  });
});

describe("QA fixes", () => {
  it("QA-01: an expiry before the start is caught before sending", () => {
    const body = { valid_from: "2026-12-01", expires_on: "2026-11-01", purposes: ["placement"], user_ids: ["u1"], agreement_reference: "MoU" };
    expect(permissionProblems(body, true)).toBe("The expiry date must be on or after the start date.");
    expect(permissionProblems({ ...body, expires_on: "2026-12-01" }, true)).toBe("");
  });

  it("QA-01: an incomplete permission is explained field by field and not sent", async () => {
    const calls = serve((call) => (call.url.includes("assignees") ? res([]) : res(pool({ can_manage: true }))));
    render(<InstitutionStudentPool orgId="o1" viewerId="m1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Add a data permission" }));
    fireEvent.click(screen.getByLabelText("Placement", { exact: true }));
    fireEvent.click(screen.getByRole("button", { name: "Add permission" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Enter the agreement reference. Choose the start and expiry dates. Choose at least one permitted purpose. Choose at least one person.",
    );
    expect(calls.some((c) => c.init?.method === "POST")).toBe(false);
  });

  it("QA-02: a pass-out year that is not a year is explained and not sent", async () => {
    const calls = serve(() => res(pool()));
    render(<InstitutionStudentPool orgId="o1" viewerId="u1" />);
    await screen.findByRole("table", { name: "Students" });
    const before = calls.length;
    fireEvent.change(screen.getByLabelText("Pass-out year"), { target: { value: "abcd" } });
    fireEvent.click(screen.getByRole("button", { name: "Filter" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Enter a pass-out year from 2000 to 2100.");
    expect(calls.length).toBe(before);
  });
});
