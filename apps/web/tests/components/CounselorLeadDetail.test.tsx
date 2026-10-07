import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CounselorLeadDetail from "@/components/CounselorLeadDetail";
import CounselorLeadsPanel from "@/components/CounselorLeadsPanel";
import type { CounselorLeadDetail as Detail } from "@/lib/leadHandover";

// tel-018 (spec §4; T19, T20; HO1, HO4): the counselor's lead -- return with a reason, link a suggested or searched student, unlink.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pageOf = <T,>(items: T[]) => ({ items, total: items.length, limit: 20, offset: 0 });
const detail = (over: Partial<Detail> = {}): Detail => ({
  id: "L1", lead_code: "LD-000042", name: "Asha Rao", email: "asha@example.com", phone: "+91 98765 43210", whatsapp_number: null, city: null,
  state: null, qualification: null, passing_year: null, institution: null, division: "it", subject: "Python", status: "counselling_completed",
  status_label: "Counselling Completed", source: "website", priority: "warm", created_at: "2026-10-06T05:00:00Z", stage_changed_at: "2026-10-06T05:00:00Z",
  product: null, campaign: null, telecaller: { id: "t1", full_name: "Tara Caller" }, counselor: { id: "c1", full_name: "Cara Counselor" },
  converted_user: null, message: "Hello", milestones: { student: null, items: [] }, permissions: { return: true, link: true, unlink: false }, ...over,
});
const asha = { id: "s1", full_name: "Asha Rao", email: "asha@example.com", phone: null, linked_elsewhere: false };
const taken = { id: "s2", full_name: "Asha R", email: "asha.r@example.com", phone: null, linked_elsewhere: true };
const linked = detail({
  status: "application_enrollment", status_label: "Application/Enrollment", converted_user: { id: "s1", full_name: "Asha Rao", email: "asha@example.com" },
  milestones: { student: { id: "s1", full_name: "Asha Rao", email: "asha@example.com" }, items: [] }, permissions: { return: false, link: false, unlink: true },
});

let fetchMock: ReturnType<typeof vi.fn>;
let reply: Record<string, () => Response>;
beforeEach(() => {
  reply = {
    "POST /return": () => res(detail({ status: "follow_up", counselor: null })),
    "POST /student-link": () => res(linked),
    "DELETE /student-link": () => res(detail()),
  };
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const tail = url.replace("/api/v1/counselor/leads/L1", "");
    if (reply[`${method} ${tail}`]) return Promise.resolve(reply[`${method} ${tail}`]());
    if (tail === "/link-suggestions") return Promise.resolve(res({ items: [asha] }));
    if (tail.startsWith("/link-suggestions?q=")) return Promise.resolve(res({ items: [taken] }));
    if (tail.startsWith("/timeline")) return Promise.resolve(res(pageOf([])));
    if (url.startsWith("/api/v1/counselor/leads?")) return Promise.resolve(res(pageOf([detail()])));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const body = (method: string, tail: string) => {
  const call = fetchMock.mock.calls.find(([u, i]) => (i?.method ?? "GET") === method && u === `/api/v1/counselor/leads/L1${tail}`);
  return call?.[1]?.body ? JSON.parse(String(call[1].body)) : call ? {} : undefined;
};

describe("CounselorLeadDetail", () => {
  it("returns the lead with a reason and then offers no further action", async () => {
    render(<CounselorLeadDetail initial={detail()} />);
    fireEvent.click(screen.getByRole("button", { name: "Return to telecaller" }));
    fireEvent.click(screen.getByRole("button", { name: "Return lead" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Add a reason for returning the lead.");
    fireEvent.change(screen.getByLabelText("Reason for returning"), { target: { value: "Needs fee talk" } });
    fireEvent.click(screen.getByRole("button", { name: "Return lead" }));
    expect(await screen.findByText("Lead returned to the telecaller.")).toBeInTheDocument();
    expect(body("POST", "/return")).toEqual({ reason: "Needs fee talk" });
    expect(screen.queryByRole("button", { name: "Return to telecaller" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Link / })).toBeNull();
    expect(screen.getByRole("link", { name: "Back to my leads" })).toHaveAttribute("href", "/it/counselor/leads");
  });

  it("shows the suggested match, links it after a confirm, then offers unlink", async () => {
    render(<CounselorLeadDetail initial={detail()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Link Asha Rao" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, link" }));
    expect(await screen.findByText("Student linked.")).toBeInTheDocument();
    expect(body("POST", "/student-link")).toEqual({ student_id: "s1" });
    expect(screen.getByText(/Stage:/)).toHaveTextContent("Application/Enrollment");
    fireEvent.click(screen.getByRole("button", { name: "Unlink student" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, unlink" }));
    expect(await screen.findByText("Student unlinked.")).toBeInTheDocument();
    expect(body("DELETE", "/student-link")).toEqual({});
  });

  it("searches students and marks one already linked elsewhere", async () => {
    render(<CounselorLeadDetail initial={detail()} />);
    await screen.findByRole("button", { name: "Link Asha Rao" });
    fireEvent.change(screen.getByLabelText("Search students"), { target: { value: "as" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter at least 3 characters.");
    fireEvent.change(screen.getByLabelText("Search students"), { target: { value: "asha.r" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText(/Already linked to another lead/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Link Asha R" })).toBeNull();
  });

  it("shows a refusal from the API in place", async () => {
    reply["POST /student-link"] = () => res({ detail: "This student is already linked to another lead" }, 409);
    render(<CounselorLeadDetail initial={detail()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Link Asha Rao" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, link" }));
    expect(await screen.findByText("This student is already linked to another lead")).toBeInTheDocument();
  });

  it("a converted lead offers neither return, link nor unlink", async () => {
    render(<CounselorLeadDetail initial={{ ...linked, status: "converted", status_label: "Converted", permissions: { return: false, link: false, unlink: false } }} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    for (const name of ["Return to telecaller", "Unlink student"]) expect(screen.queryByRole("button", { name })).toBeNull();
    expect(screen.getAllByText("Converted").length).toBeGreaterThan(0);
  });
});

describe("CounselorLeadsPanel", () => {
  it("lists the counselor's leads with links to the detail", async () => {
    render(<CounselorLeadsPanel division="overseas" />);
    const link = await screen.findByRole("link", { name: "LD-000042" });
    expect(link).toHaveAttribute("href", "/overseas/counselor/leads/L1");
    expect(screen.getByText("Counselling Completed")).toBeInTheDocument();
  });

  it("offers a retry when the list fails", async () => {
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({}, 500)));
    render(<CounselorLeadsPanel division="it" />);
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: "LD-000042" })).toBeInTheDocument();
  });
});
