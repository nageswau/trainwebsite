import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateJourney from "@/components/RecruiterCandidateJourney";
import type { CandidateJourney } from "@/lib/candidateJourney";

// rec-036 (CI7, AC2): the candidate's §27 journey -- each stage with its dates, "Not yet" for a stage not reached, the external
// candidate without training stages, and the load error with Retry.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const FULL: CandidateJourney = {
  lead: { lead_code: "LD-000042", source: "college", created_at: "2025-12-01T05:00:00Z", converted_at: "2025-12-20T05:00:00Z" },
  enrolments: [{ program: "Python Full Stack", batch: "PFS-Jan", enrolled_on: "2026-01-05", status: "completed" }],
  certificates: [{ program: "Python Full Stack", certificate_no: "EDU-CERT-2026-AB12", issued_on: "2026-03-09" }],
  candidate: { added_at: "2026-03-10T05:00:00Z", opted_in_at: "2026-03-10T05:00:00Z" },
  applications: { count: 2, first_at: "2026-03-15T05:00:00Z" },
  placements: [{ company: "ABC Technologies", position: "Python Developer", joined_on: "2026-05-04" }],
};

let body: CandidateJourney;
let fails: boolean;
beforeEach(() => {
  body = FULL;
  fails = false;
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(fails ? res({ detail: "boom" }, 500) : res(body))));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const stage = (name: string) => screen.getByRole("listitem", { name });

describe("RecruiterCandidateJourney (rec-036)", () => {
  it("shows the five stages in order, each with its dates", async () => {
    render(<RecruiterCandidateJourney candidateId="C1" />);
    const list = await screen.findByRole("list", { name: "Candidate journey" });
    expect(within(list).getAllByRole("listitem").map((li) => li.getAttribute("aria-label"))).toEqual([
      "Lead", "IT student", "Trained", "Recruiter candidate", "Placed",
    ]);
    expect(stage("Lead").textContent).toContain("LD-000042");
    expect(stage("Lead").textContent).toContain("College");
    expect(stage("IT student").textContent).toContain("Python Full Stack");
    expect(stage("IT student").textContent).toContain("Completed");
    expect(stage("Trained").textContent).toContain("EDU-CERT-2026-AB12");
    expect(stage("Recruiter candidate").textContent).toContain("2 applications");
    expect(stage("Placed").textContent).toContain("ABC Technologies");
    expect(stage("Placed").textContent).toContain("Python Developer");
    expect(fetch).toHaveBeenCalledWith("/api/v1/recruiter/candidates/C1/journey", expect.anything());
  });

  it("marks a stage not reached as Not yet", async () => {
    body = { ...FULL, certificates: [], placements: [], applications: { count: 0, first_at: null } };
    render(<RecruiterCandidateJourney candidateId="C1" />);
    await screen.findByRole("list", { name: "Candidate journey" });
    expect(stage("Trained").textContent).toContain("Not yet");
    expect(stage("Placed").textContent).toContain("Not yet");
    expect(stage("Recruiter candidate").textContent).toContain("No applications yet");
  });

  it("an external candidate has no training stages", async () => {
    body = { lead: null, enrolments: [], certificates: [], candidate: { added_at: "2026-03-10T05:00:00Z", opted_in_at: null }, applications: { count: 0, first_at: null }, placements: [] };
    render(<RecruiterCandidateJourney candidateId="C1" />);
    await screen.findByRole("list", { name: "Candidate journey" });
    expect(stage("Lead").textContent).toContain("No linked lead");
    expect(stage("IT student").textContent).toContain("Not an EduSphere IT student");
  });

  it("shows a load error with Retry", async () => {
    fails = true;
    render(<RecruiterCandidateJourney candidateId="C1" />);
    expect((await screen.findByRole("alert")).textContent).toContain("Unable to load the journey");
    fails = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByRole("list", { name: "Candidate journey" });
  });
});
