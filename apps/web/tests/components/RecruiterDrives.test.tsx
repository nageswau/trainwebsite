import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterDriveDetail from "@/components/RecruiterDriveDetail";
import RecruiterDrives from "@/components/RecruiterDrives";
import type { Drive, DriveList } from "@/lib/recruiterDrives";

// rec-029 (DEC-SCOPE-176): the drives list (search, status, empty / error states, "+ New drive" only for writers) and a drive's page
// (the funnel, Edit only for writers, adding a candidate through the drive sends its drive_id).
const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }), usePathname: () => "/recruiter/drives", useSearchParams: () => new URLSearchParams() }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const drive = (over: Partial<Drive> = {}): Drive => ({
  id: "d1", code: "DRV-000001", status: "planned", status_label: "Planned", drive_date: "2026-11-20", job_role: "Graduate Engineer Trainee",
  vacancies: 40, eligibility: "B.Tech 2026", students_registered: 200, students_attended: 100,
  company: { id: "c1", code: "CMP-000001", name: "XYZ Technologies" }, college: { org_id: "o1", code: "ORG-000001", name: "ABC College", city: "Kochi" },
  can_edit: true, created_at: "2026-10-11T00:00:00Z", updated_at: "2026-10-11T00:00:00Z",
  funnel: { registered: 200, attended: 100, tagged: 40, shortlisted: 35, interviewed: 25, selected: 12, joined: 10 },
  requirements: [{ id: "j1", code: "REQ-000001", title: "GET", status: "sourcing", open: true }, { id: "j2", code: "REQ-000002", title: "SDE", status: "closed", open: false }],
  statuses: [{ key: "sourced", label: "Sourced", initial: true }, { key: "shortlisted", label: "Shortlisted", initial: true }, { key: "joined", label: "Joined", initial: false }],
  ...over,
});
const list = (over: Partial<DriveList> = {}): DriveList => ({ items: [{ ...drive(), requirement_count: 2 }], total: 1, limit: 50, offset: 0, can_create: true, ...over });
const noCandidates = { items: [], total: 0, limit: 50, offset: 0 };
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  push.mockReset();
  refresh.mockReset();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("RecruiterDrives", () => {
  it("lists drives with their college, company and counts, and offers a new drive to writers", async () => {
    fetchMock.mockResolvedValueOnce(res(list()));
    render(<RecruiterDrives />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading drives…");
    const item = await screen.findByRole("listitem");
    expect(within(item).getByRole("link", { name: /DRV-000001/ })).toHaveAttribute("href", "/recruiter/drives/d1");
    expect(item).toHaveTextContent("ABC College, Kochi");
    expect(item).toHaveTextContent("XYZ Technologies");
    expect(item).toHaveTextContent("200 registered · 100 attended");
    expect(screen.getByRole("button", { name: "+ New drive" })).toBeInTheDocument();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/recruiter/drives?limit=50&offset=0");
  });

  it("filters by status and search, and shows the empty state without a create button for readers", async () => {
    fetchMock.mockImplementation(async () => res(list({ items: [], total: 0, can_create: false })));
    render(<RecruiterDrives />);
    expect(await screen.findByText("No campus drives yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "+ New drive" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "completed" } });
    await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/recruiter/drives?limit=50&offset=0&status=completed", expect.anything()));
    fireEvent.change(screen.getByLabelText("Search drives"), { target: { value: "ABC" } });
    fireEvent.submit(screen.getByRole("search"));
    await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/recruiter/drives?limit=50&offset=0&status=completed&q=ABC", expect.anything()));
    expect(await screen.findByText("No drives match these filters.")).toBeInTheDocument();
  });

  it("shows the API's message and retries", async () => {
    fetchMock.mockResolvedValueOnce(res({ detail: "Recruiter role required" }, 403)).mockResolvedValueOnce(res(list()));
    render(<RecruiterDrives />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Recruiter role required");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("listitem")).toBeInTheDocument();
  });
});

describe("RecruiterDriveDetail", () => {
  it("shows the funnel in source order and the requirements", async () => {
    fetchMock.mockImplementation(async () => res(noCandidates));
    render(<RecruiterDriveDetail initial={drive()} />);
    const funnel = screen.getByRole("list", { name: "Drive funnel" });
    expect(within(funnel).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Registered200", "Attended100", "Shortlisted35", "Interviewed25", "Selected12", "Joined10",
    ]);
    expect(screen.getByRole("link", { name: "XYZ Technologies" })).toHaveAttribute("href", "/recruiter/companies/c1");
    expect(screen.getByRole("link", { name: /REQ-000001/ })).toHaveAttribute("href", "/recruiter/requirements/j1");
    expect(await screen.findByText("No candidates added through this drive yet.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Add candidate/ })).toHaveLength(1); // the closed requirement takes none
    expect(screen.getByRole("button", { name: "Edit drive" })).toBeInTheDocument();
  });

  it("is read only without can_edit", async () => {
    fetchMock.mockImplementation(async () => res(noCandidates));
    render(<RecruiterDriveDetail initial={drive({ can_edit: false })} />);
    await screen.findByText("No candidates added through this drive yet.");
    expect(screen.queryByRole("button", { name: "Edit drive" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Add candidate/ })).toBeNull();
  });

  it("adds a candidate through the drive with its drive_id, then reloads the drive and its candidates", async () => {
    const tagged = { items: [{ application_id: "a1", candidate: { id: "k1", code: "CAN-000001", name: "Rahul Kumar" }, requirement: { id: "j1", code: "REQ-000001", title: "GET" }, status: "sourced", status_label: "Sourced" }], total: 1, limit: 50, offset: 0 };
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.startsWith("/api/v1/recruiter/candidates?")) return res({ items: [{ id: "k1", name: "Rahul Kumar", candidate_code: "CAN-000001" }], total: 1 });
      if (url === "/api/v1/recruiter/requirements/j1/candidates" && init?.method === "POST") return res({ application: { id: "a1", status: "sourced", candidate: { id: "k1", code: "CAN-000001", name: "Rahul Kumar" }, allowed_statuses: [] } }, 201);
      if (url === "/api/v1/recruiter/drives/d1") return res(drive({ funnel: { ...drive().funnel, tagged: 41 } }));
      return res(fetchMock.mock.calls.some(([u, i]) => (i as RequestInit | undefined)?.method === "POST" && String(u).includes("/candidates")) ? tagged : noCandidates);
    });
    render(<RecruiterDriveDetail initial={drive()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add candidate to GET" }));
    const box = screen.getByRole("combobox", { name: "Candidate" });
    fireEvent.change(box, { target: { value: "Rahul" } });
    fireEvent.click(await screen.findByRole("option", { name: /Rahul Kumar/ }));
    fireEvent.click(screen.getByRole("button", { name: "Add candidate" }));
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([, i]) => (i as RequestInit | undefined)?.method === "POST");
      expect(JSON.parse(String((post?.[1] as RequestInit).body))).toEqual({ candidate_id: "k1", status: "sourced", drive_id: "d1" });
    });
    expect(await screen.findByRole("link", { name: "Rahul Kumar" })).toHaveAttribute("href", "/recruiter/candidates/k1");
    // QA29-03: stacked items, not a table that scrolls sideways at phone width
    const items = within(screen.getByRole("list", { name: "Candidates from this drive" })).getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual(["Rahul Kumar CAN-000001GET · Sourced"]);
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Candidate added through this drive.");
  });
});
