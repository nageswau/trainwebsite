import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterWebsiteRegistrations from "@/components/RecruiterWebsiteRegistrations";
import { WEBSITE_REGISTRATIONS_URL, type WebsiteRegistration } from "@/lib/websiteRegistrations";

// hrc-025 (DEC-SCOPE-402): the New Website Registrations list -- its columns, the "Show" filter kept in the URL (?view=), the SLA badge,
// a row the reader cannot open (the HR Manager), and the loading, empty and error states.
let query = "";
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn() }), usePathname: () => "/recruiter/website-registrations", useSearchParams: () => new URLSearchParams(query),
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row: WebsiteRegistration = {
  id: "c1", candidate_code: "CAN-000101", name: "Asha Web", registered_at: "2026-11-04T06:00:00Z", location: "Pune", skills: ["Python", "SQL", "Django"],
  skill_count: 5, completeness: 45, owner: { id: "u1", full_name: "Priya Recruiter", active: true }, engagement: { key: "contacted", label: "Contacted" },
  first_contact_at: "2026-11-04T08:00:00Z", next_follow_up_at: "2026-11-06T05:00:00Z", conversion: "applied", contact_sla: "met", duplicate_review: false,
  can_open: true,
};
const late: WebsiteRegistration = {
  ...row, id: "c2", name: "Ravi Late", owner: null, skills: [], skill_count: 0, engagement: { key: "new", label: "New" }, first_contact_at: null,
  next_follow_up_at: null, conversion: "registered", contact_sla: "breached", duplicate_review: true, can_open: false,
};
let reply: () => Promise<Response>;
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  query = "";
  push.mockReset();
  reply = () => Promise.resolve(res({ items: [row, late], total: 2, limit: 100, offset: 0, sla_hours: 24 }));
  fetchMock = vi.fn(() => reply());
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("hrc-025 website registrations", () => {
  it("shows each column, links an openable row and not the other", async () => {
    render(<RecruiterWebsiteRegistrations />);
    const rows = await screen.findAllByRole("row");
    for (const name of ["Candidate", "Registered", "Skills", "Location", "Completeness", "Assigned to", "Engagement", "First contact", "Next follow-up", "Conversion"]) {
      expect(screen.getByRole("columnheader", { name })).toBeInTheDocument();
    }
    expect(within(rows[1]).getByRole("link", { name: "Asha Web" })).toHaveAttribute("href", "/recruiter/candidates/c1");
    expect(within(rows[1]).getByText("Python, SQL, Django +2")).toBeInTheDocument();
    expect(within(rows[1]).getByText("45%")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Priya Recruiter")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Applied")).toBeInTheDocument();
    expect(within(rows[2]).queryByRole("link")).toBeNull();
    expect(within(rows[2]).getByText("Ravi Late")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Unassigned")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Not contacted")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Duplicate review")).toBeInTheDocument();
  });

  it("highlights a breached contact SLA and states the target", async () => {
    render(<RecruiterWebsiteRegistrations />);
    const rows = await screen.findAllByRole("row");
    expect(within(rows[2]).getByText("SLA breached")).toHaveClass("badge");
    expect(within(rows[1]).queryByText("SLA breached")).toBeNull();
    expect(screen.getByText(/first call or message within 24 hours/i)).toBeInTheDocument();
  });

  it("the Show filter pushes ?view= and a URL value is sent to the API", async () => {
    render(<RecruiterWebsiteRegistrations />);
    await screen.findAllByRole("row");
    fireEvent.change(screen.getByLabelText("Show"), { target: { value: "unassigned" } });
    expect(push).toHaveBeenCalledWith("/recruiter/website-registrations?view=unassigned", { scroll: false });
    cleanup();
    fetchMock.mockClear();
    query = "view=duplicate_review";
    render(<RecruiterWebsiteRegistrations />);
    await screen.findAllByRole("row");
    expect(String(fetchMock.mock.calls[0][0])).toBe(`${WEBSITE_REGISTRATIONS_URL}?limit=100&offset=0&view=duplicate_review`);
    expect(screen.getByLabelText("Show")).toHaveValue("duplicate_review");
  });

  it("ignores an unknown view in the URL", async () => {
    query = "view=placed";
    render(<RecruiterWebsiteRegistrations />);
    await screen.findAllByRole("row");
    expect(String(fetchMock.mock.calls[0][0])).toBe(`${WEBSITE_REGISTRATIONS_URL}?limit=100&offset=0`);
  });

  it("shows loading, then the empty state, filtered or not", async () => {
    reply = () => Promise.resolve(res({ items: [], total: 0, limit: 100, offset: 0, sla_hours: 24 }));
    render(<RecruiterWebsiteRegistrations />);
    expect(screen.getByText("Loading website registrations…")).toBeInTheDocument();
    expect(await screen.findByText("No website registrations yet.")).toBeInTheDocument();
    cleanup();
    query = "view=new";
    render(<RecruiterWebsiteRegistrations />);
    expect(await screen.findByText("No website registrations match this filter.")).toBeInTheDocument();
  });

  it("shows an error with Retry that reloads", async () => {
    reply = () => Promise.resolve(res({ detail: "boom" }, 500));
    render(<RecruiterWebsiteRegistrations />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load website registrations.");
    reply = () => Promise.resolve(res({ items: [row], total: 1, limit: 100, offset: 0, sla_hours: 24 }));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: "Asha Web" })).toBeInTheDocument();
  });
});
