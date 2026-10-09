import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import UniversityMessages from "@/components/UniversityMessages";
import type { UniversityMessage } from "@/lib/partnershipComms";

// upc-012 (UC5-UC9; AC1, AC2, the no-email edge): the Messages section of a university -- the contact picker, Send WhatsApp / Send email
// disabled with a reason, WhatsApp recorded only on confirm, an email queued and its status shown, and the list states.
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn(), replace: vi.fn() }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pageOf = (items: unknown[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const message = (over: Partial<UniversityMessage> = {}): UniversityMessage => ({
  id: "M1", university_id: "U1", contact: { id: "K1", name: "Priya Raman" }, channel: "email", template: { id: "T1", name: "Proposal" },
  subject: "Partnership proposal", body: "Dear Priya", delivery_status: "sent", sent_at: "2026-10-08T05:30:00Z",
  sender: { id: "m1", full_name: "Maya Manager" }, ...over,
});
const contacts = [
  { id: "K1", name: "Priya Raman", email: "priya@abc.ac.uk", whatsapp_to: "919845000000" },
  { id: "K2", name: "Ravi Kumar", email: null, whatsapp_to: null },
];

let items: UniversityMessage[];
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  refresh.mockReset();
  items = [message(), message({ id: "M2", channel: "whatsapp", subject: null, delivery_status: null, template: null, body: "Hi Priya" })];
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") return Promise.resolve(res(message({ id: "M3", delivery_status: "queued" }), 201));
    if (url.includes("/templates")) return Promise.resolve(res(pageOf([{ id: "T1", name: "Proposal" }])));
    if (url.includes("/render")) return Promise.resolve(res({ template: { id: "T1", name: "Proposal", channel: "email" }, subject: "Partnership proposal for ABC", body: "Dear Priya Raman", missing: [] }));
    return Promise.resolve(res(pageOf(items)));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("UniversityMessages (upc-012)", () => {
  it("lists messages with the email's delivery status (AC1)", async () => {
    items = [message({ delivery_status: "failed" }), ...items.slice(1)];
    render(<UniversityMessages universityId="U1" contacts={contacts} canWrite />);
    expect(screen.getByText("Loading messages…")).toBeTruthy();
    const [email, whatsapp] = within(await screen.findByRole("list", { name: "Messages" })).getAllByRole("listitem");
    expect(email.textContent).toContain("To Priya Raman");
    expect(email.textContent).toContain("Partnership proposal");
    expect(email.textContent).toContain("This email was not delivered");
    expect(whatsapp.textContent).toContain("Hi Priya");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/partnership/universities/U1/messages?limit=50");
  });

  it("disables both buttons with the reason for a contact without a number or an email (edge)", async () => {
    render(<UniversityMessages universityId="U1" contacts={contacts} canWrite />);
    await screen.findByRole("list", { name: "Messages" });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "K2" } });
    expect((screen.getByRole("button", { name: "Send WhatsApp" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Send email" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/No usable mobile number for Ravi Kumar\. No email address for Ravi Kumar\./)).toBeTruthy();
  });

  it("sends an email from a template to the chosen contact and refreshes the page", async () => {
    render(<UniversityMessages universityId="U1" contacts={contacts} canWrite />);
    await screen.findByRole("list", { name: "Messages" });
    fireEvent.click(screen.getByRole("button", { name: "Send email" }));
    const composer = await screen.findByRole("form", { name: "Email message" });
    await within(composer).findByRole("option", { name: "Proposal" });
    fireEvent.change(within(composer).getByLabelText("Template"), { target: { value: "T1" } });
    await waitFor(() => expect((within(composer).getByLabelText("Message") as HTMLTextAreaElement).value).toBe("Dear Priya Raman"));
    fireEvent.click(within(composer).getByRole("button", { name: /Send email/ }));
    expect(await screen.findByText("Email to Priya Raman queued for sending.")).toBeTruthy();
    const post = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "POST")!;
    expect(String(post[0])).toBe("/api/v1/partnership/messages");
    expect(JSON.parse(String((post[1] as RequestInit).body))).toMatchObject({ contact_id: "K1", channel: "email", template_id: "T1", subject: "Partnership proposal for ABC" });
    expect(String(fetchMock.mock.calls.find(([u]) => String(u).includes("/render"))![0])).toContain("contact_id=K1");
    expect(refresh).toHaveBeenCalled();
  });

  it("shows no send controls to a reader, and says when there is no contact", async () => {
    const { unmount } = render(<UniversityMessages universityId="U1" contacts={contacts} canWrite={false} />);
    await screen.findByRole("list", { name: "Messages" });
    expect(screen.queryByRole("button", { name: "Send WhatsApp" })).toBeNull();
    unmount();
    render(<UniversityMessages universityId="U1" contacts={[]} canWrite />);
    expect(await screen.findByText("Add a contact to send a message.")).toBeTruthy();
  });
});
