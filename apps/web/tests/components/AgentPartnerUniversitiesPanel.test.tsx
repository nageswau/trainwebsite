import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AgentPartnerUniversitiesPanel from "@/components/AgentPartnerUniversitiesPanel";

const item = { id: "u1", slug: "usw", name: "University of South Wales", logo_url: null, city: "Cardiff Campus", campuses: ["Cardiff Campus"], country: { id: "c1", name: "United Kingdom", iso2: "GB" }, course_count: 33 };
const commission = { percent: "13.00", amount: null, currency: null, note: "0.13" };
const course = { id: "k1", title: "MSc Data Science", level: "Postgraduate", category: "IT", duration: "1 year", campus: "Newport Campus", fee_text: "GBP 15,000", intake_text: "September", tuition_fee: null, intake: null };
const detail = (over: Record<string, unknown> = {}) => ({ university: { ...item, website: "https://www.southwales.ac.uk", overview: "A Welsh university.", fee_structure: null, deadlines: null, scholarships: null, courses: [course], ...over } });
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }), usePathname: () => "/overseas/agent/partner-universities", useSearchParams: () => new URLSearchParams() }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const route = (list: unknown, one: unknown) => vi.fn(async (url: string) => (url.includes("/u1") ? res(one) : res(list)));

describe("AgentPartnerUniversitiesPanel", () => {
  it("shows the country flag in the list (PUB-023)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => res({ items: [item], total: 1 })));
    const { container } = render(<AgentPartnerUniversitiesPanel memberRole="staff" />);
    await waitFor(() => expect(screen.getByText("University of South Wales")).toBeTruthy());
    const flag = container.querySelector('td img.country-flag[src="/flags/gb.svg"]');
    expect(flag).not.toBeNull();
    expect(flag!.parentElement!.textContent).toBe("United Kingdom");
  });
  it("shows the agent commission column for a Master", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => res({ items: [{ ...item, agent_commission: commission }], total: 1 })));
    render(<AgentPartnerUniversitiesPanel memberRole="master" />);
    await waitFor(() => expect(screen.getByText("University of South Wales")).toBeTruthy());
    expect(screen.getByRole("columnheader", { name: "Agent commission" })).toBeTruthy();
    expect(screen.getByText("13.00%")).toBeTruthy();
  });
  it("has no commission column for staff", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => res({ items: [item], total: 1 })));
    render(<AgentPartnerUniversitiesPanel memberRole="staff" />);
    await waitFor(() => expect(screen.getByText("University of South Wales")).toBeTruthy());
    expect(screen.queryByRole("columnheader", { name: "Agent commission" })).toBeNull();
  });
  it("opens the detail on clicking a name and lists the courses, with the Master's commission", async () => {
    vi.stubGlobal("fetch", route({ items: [{ ...item, agent_commission: commission }], total: 1 }, detail({ agent_commission: commission })));
    render(<AgentPartnerUniversitiesPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "University of South Wales" }));
    expect(await screen.findByText("MSc Data Science")).toBeTruthy();
    expect(screen.getByText("GBP 15,000")).toBeTruthy();
    expect(screen.getByText("Newport Campus")).toBeTruthy();
    expect(screen.getByText("A Welsh university.")).toBeTruthy();
    expect(screen.getByText("Agent commission")).toBeTruthy();
    expect(screen.getByText("13.00%")).toBeTruthy();
    const link = screen.getByRole("link", { name: "https://www.southwales.ac.uk" });
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });
  it("shows staff no commission in the detail, and no link for an unsafe website", async () => {
    vi.stubGlobal("fetch", route({ items: [item], total: 1 }, detail({ website: "javascript:alert(1)" })));
    render(<AgentPartnerUniversitiesPanel memberRole="staff" />);
    fireEvent.click(await screen.findByRole("button", { name: "University of South Wales" }));
    expect(await screen.findByText("MSc Data Science")).toBeTruthy();
    expect(screen.queryByText("Agent commission")).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
  });
  it("renders deadlines and scholarships as separate list items, and nothing for empty lists", async () => {
    vi.stubGlobal("fetch", route({ items: [item], total: 1 }, detail({ deadlines: ["Jan Intake: Late November", "May Intake: Mid-April"], scholarships: [], fee_structure: "Line 1" + String.fromCharCode(10) + "Line 2" })));
    render(<AgentPartnerUniversitiesPanel memberRole="staff" />);
    fireEvent.click(await screen.findByRole("button", { name: "University of South Wales" }));
    expect(await screen.findByText("Jan Intake: Late November")).toBeTruthy();
    expect(screen.getByText("May Intake: Mid-April").tagName).toBe("LI");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.queryByText("Scholarships")).toBeNull();
    expect((screen.getByText(/Line 1/) as HTMLElement).style.whiteSpace).toBe("pre-line");
  });
  it("hides the commission from staff even when the payload carries it", async () => {
    vi.stubGlobal("fetch", route({ items: [{ ...item, agent_commission: commission }], total: 1 }, detail({ agent_commission: commission })));
    render(<AgentPartnerUniversitiesPanel memberRole="staff" />);
    await screen.findByText("University of South Wales");
    expect(screen.queryByRole("columnheader", { name: "Agent commission" })).toBeNull();
    expect(screen.queryByText("13.00%")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "University of South Wales" }));
    expect(await screen.findByText("MSc Data Science")).toBeTruthy();
    expect(screen.queryByText("Agent commission")).toBeNull();
    expect(screen.queryByText("13.00%")).toBeNull();
  });
  it("shows a Master each course's effective commission with its source (ccrm-051)", async () => {
    const own = { ...course, agent_commission_effective: { percent: "12.00", amount: null, currency: null, note: null, source: "course" } };
    const fallback = { ...course, id: "k2", title: "MBA", agent_commission_effective: { ...commission, source: "university" } };
    const none = { ...course, id: "k3", title: "BSc Nursing", agent_commission_effective: null };
    vi.stubGlobal("fetch", route({ items: [item], total: 1 }, detail({ agent_commission: commission, courses: [own, fallback, none] })));
    render(<AgentPartnerUniversitiesPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "University of South Wales" }));
    expect(await screen.findByRole("columnheader", { name: "Agent commission" })).toBeTruthy();
    const cell = (title: string) => screen.getByText(title).closest("tr")!.lastElementChild!.textContent;
    expect(cell("MSc Data Science")).toBe("12.00% (course)");
    expect(cell("MBA")).toBe("13.00% (university)");
    expect(cell("BSc Nursing")).toBe("—");
  });
  it("has no course commission column for staff, even if a course carries it", async () => {
    const own = { ...course, agent_commission_effective: { percent: "12.00", amount: null, currency: null, note: null, source: "course" } };
    vi.stubGlobal("fetch", route({ items: [item], total: 1 }, detail({ courses: [own] })));
    render(<AgentPartnerUniversitiesPanel memberRole="staff" />);
    fireEvent.click(await screen.findByRole("button", { name: "University of South Wales" }));
    expect(await screen.findByText("MSc Data Science")).toBeTruthy();
    expect(screen.queryByRole("columnheader", { name: "Agent commission" })).toBeNull();
    expect(screen.queryByText(/12\.00%/)).toBeNull();
  });
  it("shows an alert when the list cannot be loaded", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => res({ detail: "boom" }, 500)));
    render(<AgentPartnerUniversitiesPanel memberRole="master" />);
    expect((await screen.findByRole("alert")).textContent).toContain("couldn't complete");
  });
  it("says so when nothing matches", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => res({ items: [], total: 0 })));
    render(<AgentPartnerUniversitiesPanel memberRole="staff" />);
    expect(await screen.findByText("No partner universities found")).toBeTruthy();
  });
});
