import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmOrganizationSchoolActivity from "@/components/BdmOrganizationSchoolActivity";
import type { SchoolActivity } from "@/lib/bdmSchoolActivity";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const metric = (key: string, label: string, completed: number, pending: number) => ({ key, label, tracked: true, completed, pending });
const linked: SchoolActivity = {
  linked: true, school: { name: "St Mary School", school_code: "AB12CD34" }, total_students: 800,
  metrics: [
    metric("career_guidance", "Career Guidance", 650, 150), metric("psychometric_test", "Psychometric Test", 580, 220),
    metric("university_guidance", "University Guidance", 150, 650),
    { key: "student_profile_completion", label: "Student Profile Completion", tracked: false, completed: null, pending: null },
  ],
};
const unlinked: SchoolActivity = { linked: false, school: null, total_students: null, metrics: [] };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmOrganizationSchoolActivity (bdm-020 §3)", () => {
  it("shows the linked School's total and each metric's completed and pending counts", () => {
    render(<BdmOrganizationSchoolActivity orgId="o1" initial={linked} />);
    const region = screen.getByRole("region", { name: "School activity" });
    expect(region).toHaveTextContent("St Mary School (School ID AB12CD34) · 800 students");
    const row = within(region).getByRole("row", { name: /Career Guidance/ });
    expect(within(row).getAllByRole("cell").map((c) => c.textContent)).toEqual(["650", "150"]);
    expect(within(region).getByRole("columnheader", { name: "Completed" })).toBeInTheDocument();
  });

  it("says a metric without School-module data is not tracked, never a zero", () => {
    render(<BdmOrganizationSchoolActivity orgId="o1" initial={linked} />);
    const row = screen.getByRole("row", { name: /Student Profile Completion/ });
    expect(row).toHaveTextContent("Not tracked");
    expect(row).not.toHaveTextContent("0");
  });

  it("says an organization without a linked School is not onboarded yet", () => {
    render(<BdmOrganizationSchoolActivity orgId="o1" initial={unlinked} />);
    const region = screen.getByRole("region", { name: "School activity" });
    expect(region).toHaveTextContent("Not onboarded yet. Counts appear once Overseas Admin links the School.");
    expect(within(region).queryByRole("table")).toBeNull();
  });

  it("offers Try again when the first read failed, and shows the counts it then reads", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(res({ detail: "boom" }, 500)).mockResolvedValueOnce(res(linked));
    vi.stubGlobal("fetch", fetch);
    render(<BdmOrganizationSchoolActivity orgId="o1" initial={null} />);
    expect(screen.getByText("Unable to load the school activity.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled()); // the failed retry keeps the error
    expect(screen.getByText("Unable to load the school activity.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("row", { name: /Career Guidance/ })).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/v1/bdm/organizations/o1/school-activity", { method: "GET" });
  });

  it("ignores a malformed answer instead of crashing", async () => {
    const fetch = vi.fn().mockResolvedValue(res({ unexpected: true }));
    vi.stubGlobal("fetch", fetch);
    render(<BdmOrganizationSchoolActivity orgId="o1" initial={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled());
    expect(screen.getByText("Unable to load the school activity.")).toBeInTheDocument();
  });
});
