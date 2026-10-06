import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminSchoolCreatePanel from "@/components/AdminSchoolCreatePanel";
import AdminSchoolOnboarding from "@/components/AdminSchoolOnboarding";
import AdminSchoolOnboardingRequests from "@/components/AdminSchoolOnboardingRequests";
import type { OnboardingItem } from "@/lib/bdmOnboarding";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const item = (over: Partial<OnboardingItem> = {}): OnboardingItem => ({
  id: "r1", status: "pending", note: "Ready from June", created_at: "2026-10-06T05:00:00Z", resolved_at: null, resolution: null, reject_reason: null,
  requested_by: { id: "b1", full_name: "Asha" }, assigned_bdm: { id: "b1", full_name: "Asha", active: true },
  organization: {
    id: "o1", code: "ORG-000001", name: "St Mary School", city: "Kochi", state: "Kerala", address: "1 Hill Road", phone: "0484 000", email: "office@stmary.local",
    website: "https://stmary.local", board: "CBSE", grade_from: 1, grade_to: 12,
  },
  primary_contact: { name: "Dr Rao", email: "rao@stmary.local", phone: null },
  mou: { reference: "MOU-14", signed_on: "2026-01-10" },
  school: null,
  ...over,
});
const page = (items: OnboardingItem[], total = items.length) => ({ items, total, limit: 20, offset: 0 });
const queue = (onUse = vi.fn(), onResolved = vi.fn()) => render(<AdminSchoolOnboardingRequests selectedId={null} version={0} onUse={onUse} onResolved={onResolved} />);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminSchoolOnboardingRequests (bdm-018 §6)", () => {
  it("loads the pending requests, then shows each with its organization and note", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res(page([item()])));
    vi.stubGlobal("fetch", fetchMock);
    queue();
    expect(screen.getByText("Loading onboarding requests…")).toBeInTheDocument();
    const entry = await screen.findByRole("listitem");
    expect(entry).toHaveTextContent("ORG-000001 · St Mary School");
    expect(entry).toHaveTextContent("Requested by Asha");
    expect(entry).toHaveTextContent("Ready from June");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/overseas-admin/bdm-onboarding-requests?status=pending&limit=20&offset=0");
  });

  it("says when nothing is waiting, and explains a failed load with a retry", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res({ detail: "Overseas Admin role required" }, 403)).mockResolvedValueOnce(res(page([]))));
    queue();
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load onboarding requests.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No onboarding requests waiting.")).toBeInTheDocument();
  });

  it("hands a request to the create form", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([item()]))));
    const onUse = vi.fn();
    queue(onUse);
    fireEvent.click(await screen.findByRole("button", { name: "Use for new school" }));
    expect(onUse).toHaveBeenCalledWith(item());
  });

  it("rejects with a required reason, then drops the request and says so", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(res(page([item()]))).mockResolvedValueOnce(res(item({ status: "rejected", reject_reason: "Board missing" })));
    vi.stubGlobal("fetch", fetchMock);
    const onResolved = vi.fn();
    queue(vi.fn(), onResolved);
    fireEvent.click(await screen.findByRole("button", { name: "Reject" }));
    const reason = screen.getByLabelText("Reason (sent to the BDM)");
    expect(reason).toBeRequired();
    fireEvent.change(reason, { target: { value: "Board missing" } });
    fireEvent.click(screen.getByRole("button", { name: "Reject request" }));
    expect(await screen.findByText("Request from ORG-000001 rejected. The BDM has been told why.")).toBeInTheDocument();
    expect(screen.queryByRole("listitem")).toBeNull();
    expect(onResolved).toHaveBeenCalledWith("r1");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/v1/overseas-admin/bdm-onboarding-requests/r1/reject");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ reason: "Board missing" });
  });

  it("links an existing School by its ID, and shows a refusal in place", async () => {
    const linked = item({ status: "completed", resolution: "linked", school: { id: "s1", name: "St Mary", school_code: "AB12CD34" } });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(res(page([item()])))
      .mockResolvedValueOnce(res({ detail: { message: "This School is already linked to another organization", code: "school_linked" } }, 409))
      .mockResolvedValueOnce(res(linked));
    vi.stubGlobal("fetch", fetchMock);
    queue();
    fireEvent.click(await screen.findByRole("button", { name: "Link existing school" }));
    fireEvent.change(screen.getByLabelText("School ID"), { target: { value: "ab12cd34" } });
    fireEvent.click(screen.getByRole("button", { name: "Link school" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This School is already linked to another organization");
    fireEvent.click(screen.getByRole("button", { name: "Link school" }));
    expect(await screen.findByText("ORG-000001 is now linked to St Mary (AB12CD34).")).toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ school_code: "ab12cd34" });
  });

  it("QA18-01: a server error on reject says the outcome is unknown", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res(page([item()]))).mockResolvedValueOnce(new Response("boom", { status: 502 })));
    queue();
    fireEvent.click(await screen.findByRole("button", { name: "Reject" }));
    fireEvent.change(screen.getByLabelText("Reason (sent to the BDM)"), { target: { value: "No" } });
    fireEvent.click(screen.getByRole("button", { name: "Reject request" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The request could not be confirmed. Reload the page to check before trying again.");
  });

  it("QA18-02: a long queue scrolls inside its own keyboard-reachable region instead of stretching the page", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([item()]))));
    queue();
    const list = await screen.findByRole("list", { name: "Onboarding requests" });
    expect(list).toHaveAttribute("tabindex", "0");
    expect(list.style.overflowY).toBe("auto");
    expect(list.style.maxHeight).not.toBe("");
  });

  it("offers more when the queue has another page", async () => {
    const second = item({ id: "r2", organization: { ...item().organization, id: "o2", code: "ORG-000002" } });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res(page([item()], 2))).mockResolvedValueOnce(res({ ...page([second], 2), offset: 20 })));
    queue();
    fireEvent.click(await screen.findByRole("button", { name: "Show more" }));
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(2));
    expect(screen.queryByRole("button", { name: "Show more" })).toBeNull();
  });
});

describe("AdminSchoolCreatePanel with a request (bdm-018 §6)", () => {
  it("prefills from the organization, says which request it serves, and sends its id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ coordinator_email: "rao@stmary.local", email_status: "sent", school_code: "AB12CD34" }, 201));
    vi.stubGlobal("fetch", fetchMock);
    const onCreated = vi.fn();
    render(<AdminSchoolCreatePanel request={item()} onClear={vi.fn()} onCreated={onCreated} />);
    expect(screen.getByText(/Creating the School for ORG-000001 · St Mary School/)).toBeInTheDocument();
    expect(screen.getByLabelText("School name")).toHaveValue("St Mary School");
    expect(screen.getByLabelText("Board")).toHaveValue("CBSE");
    expect(screen.getByLabelText("Grades available")).toHaveValue("1-12");
    expect(screen.getByLabelText("Agreement / MoU reference")).toHaveValue("MOU-14");
    expect(screen.getByLabelText("Partnership date")).toHaveValue("2026-01-10");
    expect(screen.getByLabelText("Coordinator full name")).toHaveValue("Dr Rao");
    expect(screen.getByLabelText("Coordinator email")).toHaveValue("rao@stmary.local");
    fireEvent.click(screen.getByRole("button", { name: "Create school + seed Coordinator" }));
    await screen.findByText(/School created\./);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).bdm_onboarding_request_id).toBe("r1");
    expect(screen.getByText(/Linked to ORG-000001/)).toBeInTheDocument();
    expect(onCreated).toHaveBeenCalled();
  });

  it("no longer asks for the legacy Edusphere BDM text (Q-16)", () => {
    render(<AdminSchoolCreatePanel />);
    expect(screen.queryByLabelText("Edusphere BDM")).toBeNull();
  });

  it("Clear drops the request", () => {
    const onClear = vi.fn();
    render(<AdminSchoolCreatePanel request={item()} onClear={onClear} onCreated={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(onClear).toHaveBeenCalled();
  });
});

describe("AdminSchoolOnboarding (bdm-018 §6)", () => {
  it("Use for new school fills the create form below and focuses it", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([item()]))));
    render(<AdminSchoolOnboarding />);
    fireEvent.click(await screen.findByRole("button", { name: "Use for new school" }));
    const name = screen.getByLabelText("School name");
    expect(name).toHaveValue("St Mary School");
    await waitFor(() => expect(name).toHaveFocus());
    expect(within(screen.getByRole("listitem")).getByRole("button", { name: "Use for new school" })).toHaveAttribute("aria-pressed", "true");
  });
});
