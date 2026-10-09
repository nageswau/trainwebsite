import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterShareDialog from "@/components/RecruiterShareDialog";
import type { Share } from "@/lib/recruiterShares";

// rec-019 (DEC-SCOPE-159; S1-S5): the share dialog -- the company's active contacts, the four channels, the repeat 409 and "Share again",
// the WhatsApp result.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const contact = (id: string, over: Record<string, unknown> = {}) => ({
  id, name: `Contact ${id}`, designation: null, department: null, role: null, mobile: "+919876543210", email: `${id}@example.com`, linkedin_url: null,
  preferred_channel: null, notes: null, is_primary: id === "K1", active: true, last_contacted_at: null, created_at: "", updated_at: "", ...over,
});
const share = (over: Partial<Share> = {}): Share => ({
  id: "S1", channel: "email", channel_label: "Email", requirement: { id: "J1", code: "REQ-000001", title: "Java Dev" }, company_id: "CO1",
  contact: { id: "K1", name: "Contact K1" }, note: null, message: { id: "M1", delivery_status: "queued" }, shared_by: { id: "U1", full_name: "Asha" },
  created_at: "2026-10-09T05:00:00Z", can_respond: true, items: [], ...over,
});
const people = [{ id: "C1", name: "Rahul", code: "CAN-000001" }, { id: "C2", name: "Priya", code: "CAN-000002" }];

let replies: Response[];
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  replies = [];
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") return Promise.resolve(replies.shift() ?? res({}, 500));
    if (url === "/api/v1/recruiter/requirements/J1") return Promise.resolve(res({ requirement: { id: "J1", company: { id: "CO1" } } }));
    if (url.endsWith("/CO1/contacts")) return Promise.resolve(res({ items: [contact("K1"), contact("K2", { email: null }), contact("K3", { active: false })], can_edit: true }));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("open", vi.fn());
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const posted = () => JSON.parse(fetchMock.mock.calls.find(([, init]) => init?.method === "POST")![1].body as string);

describe("RecruiterShareDialog", () => {
  it("offers only active contacts, preselects the primary and shares by email", async () => {
    const onShared = vi.fn();
    replies.push(res({ share: share({ items: [] }), whatsapp_url: null }, 201));
    render(<RecruiterShareDialog requirement={{ id: "J1", label: "Java Dev" }} companyId="CO1" candidates={people} onShared={onShared} onClose={vi.fn()} />);
    const select = await screen.findByLabelText("Contact");
    await waitFor(() => expect((select as HTMLSelectElement).value).toBe("K1"));
    expect(screen.queryByRole("option", { name: /Contact K3/ })).toBeNull();
    fireEvent.change(screen.getByLabelText(/Internal note/), { target: { value: "Top two" } });
    fireEvent.click(screen.getByRole("button", { name: "Share 2 profiles" }));
    expect(await screen.findByText(/Shared 0 profiles for Java Dev by Email with Contact K1/)).toBeTruthy();
    expect(posted()).toEqual({ requirement_id: "J1", candidate_ids: ["C1", "C2"], channel: "email", contact_id: "K1", note: "Top two" });
    expect(onShared).toHaveBeenCalled();
  });

  it("finds the company from the requirement when it is not given, and blocks email to a contact without an address", async () => {
    render(<RecruiterShareDialog requirement={{ id: "J1", label: "Java Dev" }} candidates={people} onShared={vi.fn()} onClose={vi.fn()} />);
    const select = await screen.findByLabelText("Contact");
    await waitFor(() => expect((select as HTMLSelectElement).value).toBe("K1"));
    fireEvent.change(select, { target: { value: "K2" } });
    expect(screen.getByText("This contact has no email address.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Share 2 profiles" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("lists repeats from the 409 and resends with repeat", async () => {
    replies.push(res({ detail: { message: "1 of these candidates were already shared for this requirement. Share again?", duplicates: [{ id: "C1", name: "Rahul", code: "CAN-000001" }] } }, 409));
    replies.push(res({ share: share({ channel: "other", channel_label: "Other", contact: null, message: null }), whatsapp_url: null }, 201));
    render(<RecruiterShareDialog requirement={{ id: "J1", label: "Java Dev" }} companyId="CO1" candidates={people} onShared={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByLabelText(/^Other/));
    fireEvent.change(screen.getByLabelText("Contact (optional)"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Share 2 profiles" }));
    expect(await screen.findByText(/already shared/)).toBeTruthy();
    expect(screen.getByText("Rahul (CAN-000001)")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Share again" }));
    expect(await screen.findByText(/by Other/)).toBeTruthy();
    const bodies = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST").map(([, init]) => JSON.parse(init!.body as string));
    expect(bodies[0]).toEqual({ requirement_id: "J1", candidate_ids: ["C1", "C2"], channel: "other" });
    expect(bodies[1].repeat).toBe(true);
  });

  it("records a WhatsApp share and offers wa.me", async () => {
    replies.push(res({ share: share({ channel: "whatsapp", channel_label: "WhatsApp", message: { id: "M2", delivery_status: null } }), whatsapp_url: "https://wa.me/919876543210?text=hi" }, 201));
    render(<RecruiterShareDialog requirement={{ id: "J1", label: "Java Dev" }} companyId="CO1" candidates={people} onShared={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByLabelText(/^WhatsApp/));
    await waitFor(() => expect((screen.getByLabelText("Contact") as HTMLSelectElement).value).toBe("K1"));
    fireEvent.click(screen.getByRole("button", { name: "Record and open WhatsApp" }));
    const link = await screen.findByRole("link", { name: /Open WhatsApp/ });
    expect(link.getAttribute("href")).toBe("https://wa.me/919876543210?text=hi");
    expect(window.open).toHaveBeenCalledWith("https://wa.me/919876543210?text=hi", "_blank", "noopener,noreferrer");
  });

  it("shows the API's refusal", async () => {
    replies.push(res({ detail: "Choose active candidates from the pool" }, 422));
    render(<RecruiterShareDialog requirement={{ id: "J1", label: "Java Dev" }} companyId="CO1" candidates={people} onShared={vi.fn()} onClose={vi.fn()} />);
    await waitFor(() => expect((screen.getByLabelText("Contact") as HTMLSelectElement).value).toBe("K1"));
    fireEvent.click(screen.getByRole("button", { name: "Share 2 profiles" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Choose active candidates from the pool");
  });
});
