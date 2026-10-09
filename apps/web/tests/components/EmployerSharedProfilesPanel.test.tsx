import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import EmployerSharedProfilesPanel from "@/components/EmployerSharedProfilesPanel";
import type { PortalItem } from "@/lib/recruiterShares";

// rec-019 (DEC-SCOPE-158; S8, S9): the employer's "Shared with you" panel -- the summary only, the resume link and the response.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const item = (over: Partial<PortalItem> = {}): PortalItem => ({
  id: "I1", shared_at: "2026-10-09T05:00:00Z", requirement: { code: "REQ-000001", title: "Java Dev" }, has_resume: true, response: "pending", response_label: "Pending",
  candidate: {
    code: "CAN-000001", name: "Rahul", qualification: "B.Tech", college: "JNTU", passing_year: 2022, experience_months: 26, current_company: null,
    location: "Pune", preferred_locations: ["Pune", "Hyderabad"], preferred_role: "Java Developer", notice_days: 30, skills: ["Java", "Spring"],
  },
  ...over,
});

let page: unknown;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  page = { items: [item()], total: 1, limit: 20, offset: 0 };
  fetchMock = vi.fn((_url: string, init?: RequestInit) =>
    Promise.resolve(init?.method === "PATCH" ? res(item({ response: "interested", response_label: "Interested" })) : res(page)));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("EmployerSharedProfilesPanel", () => {
  it("shows the summary and the resume link, and saves a response", async () => {
    render(<EmployerSharedProfilesPanel />);
    expect(await screen.findByRole("heading", { name: "Rahul" })).toBeTruthy();
    expect(screen.getByText("B.Tech · JNTU · 2022")).toBeTruthy();
    expect(screen.getByText("2 yrs 2 mos")).toBeTruthy();
    expect(screen.getByText("Java, Spring")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Download resume/ }).getAttribute("href")).toBe("/api/v1/employer/shared-profiles/I1/resume");
    const save = screen.getByRole("button", { name: /Save response/ }) as HTMLButtonElement;
    expect(save.disabled).toBe(true); // unchanged
    fireEvent.change(screen.getByLabelText("Your response"), { target: { value: "interested" } });
    fireEvent.click(save);
    expect(await screen.findByText("Response saved for Rahul.")).toBeTruthy();
    expect(screen.getByText("Interested", { selector: ".badge" })).toBeTruthy();
    expect(JSON.parse(fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH")![1].body as string)).toEqual({ response: "interested" });
  });

  it("says when nothing was shared and when there is no resume", async () => {
    page = { items: [], total: 0, limit: 20, offset: 0 };
    render(<EmployerSharedProfilesPanel />);
    expect(await screen.findByText("No profiles have been shared with you yet.")).toBeTruthy();
    cleanup();
    page = { items: [item({ has_resume: false })], total: 1, limit: 20, offset: 0 };
    render(<EmployerSharedProfilesPanel />);
    expect(await screen.findByText("Resume on request")).toBeTruthy();
  });
});
