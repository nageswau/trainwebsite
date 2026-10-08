import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RecruiterMessages from "@/components/RecruiterMessages";
import type { RecMessage } from "@/lib/recruiterMessages";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const page = (items: unknown[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const contact = (id: string, name: string, over: Record<string, unknown> = {}) => ({
  id, name, active: true, mobile: "98765 43210", email: `${id}@abc.example.com`, whatsapp_to: "919876543210", ...over,
});
const template = { id: "t1", channel: "whatsapp", kind: "follow_up", name: "Follow-up", subject: null, body: "Hi {name}", active: true };
const sent = (over: Partial<RecMessage> = {}): RecMessage => ({
  id: "m1", kind: "contact", company_id: "co1", contact: { id: "k1", name: "Priya" }, candidate: null, channel: "whatsapp", template: null,
  subject: null, body: "Hello earlier", delivery_status: null, sent_at: "2026-10-08T05:05:00Z", sender: { id: "u1", full_name: "Asha" }, ...over,
});

type Call = { url: string; init?: RequestInit };
function serve(routes: (url: string) => Response, onWrite: (call: Call) => Response = () => res(sent(), 201)) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const call = { url: String(url), init };
    calls.push(call);
    return Promise.resolve(init?.method && init.method !== "GET" ? onWrite(call) : routes(String(url)));
  }));
  return calls;
}
const writes = (calls: Call[]) => calls.filter((c) => c.init?.method === "POST");

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("rec-026 RecruiterMessages", () => {
  it("sends a WhatsApp to the chosen active contact and records it only on confirm (AC3)", async () => {
    const calls = serve((url) => {
      if (url.includes("/contacts")) return res({ items: [contact("k1", "Priya"), contact("k2", "Ravi", { active: false }), contact("k3", "Meera")], can_edit: true });
      if (url.includes("/templates")) return res(page([template]));
      if (url.includes("/render")) return res({ template, subject: null, body: "Hi Meera" });
      return res(page([sent()]));
    });
    const onChanged = vi.fn();
    render(<RecruiterMessages source={{ kind: "company", companyId: "co1" }} canWrite onChanged={onChanged} />);
    const picker = await screen.findByLabelText("To");
    expect(within(picker).getAllByRole("option").map((o) => o.textContent)).toEqual(["Priya", "Meera"]); // inactive contacts are not offered
    expect(await screen.findByText("Hello earlier")).toBeTruthy();
    fireEvent.change(picker, { target: { value: "k3" } });
    fireEvent.click(screen.getByRole("button", { name: "Send WhatsApp" }));
    fireEvent.change(await screen.findByLabelText("Template"), { target: { value: "t1" } });
    await waitFor(() => expect((screen.getByLabelText("Message") as HTMLTextAreaElement).value).toBe("Hi Meera"));
    expect(calls.some((c) => c.url.includes("render?template_id=t1&contact_id=k3"))).toBe(true);
    const open = screen.getByRole("link", { name: /Open WhatsApp/ });
    expect(open.getAttribute("href")).toBe("https://wa.me/919876543210?text=Hi%20Meera");
    expect(writes(calls)).toHaveLength(0);
    fireEvent.click(open);
    fireEvent.click(screen.getByRole("button", { name: "Yes, record as sent" }));
    await screen.findByText("WhatsApp to Meera recorded.");
    expect(JSON.parse(String(writes(calls)[0].init?.body))).toEqual({ contact_id: "k3", channel: "whatsapp", template_id: "t1", body: "Hi Meera" });
    expect(onChanged).toHaveBeenCalled();
  });

  it("queues an email to a candidate and shows its status (AC2); a candidate without an address can't be emailed", async () => {
    const calls = serve((url) => (url.includes("/templates") ? res(page([])) : res(page([sent({ kind: "candidate", contact: null, candidate: { id: "c1", name: "Rahul", code: "CAN-000001" }, channel: "email", subject: "Interview", delivery_status: "failed" })]))));
    const party = { kind: "candidate" as const, id: "c1", name: "Rahul", whatsappTo: null, email: "rahul@example.com" };
    render(<RecruiterMessages source={{ kind: "candidate", party }} canWrite />);
    expect(await screen.findByText(/This email was not delivered/)).toBeTruthy();
    const whatsapp = screen.getByRole("button", { name: "Send WhatsApp" }) as HTMLButtonElement;
    expect(whatsapp.disabled).toBe(true);
    expect(screen.getByText("No usable mobile number for Rahul.")).toBeTruthy();
    expect(screen.queryByLabelText("To")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Send email" }));
    fireEvent.change(await screen.findByLabelText("Subject"), { target: { value: "Interview confirmation" } });
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Dear Rahul" } });
    fireEvent.click(screen.getByRole("button", { name: "Send email" }));
    await screen.findByText("Email to Rahul queued for sending.");
    expect(JSON.parse(String(writes(calls)[0].init?.body))).toEqual({ candidate_id: "c1", channel: "email", subject: "Interview confirmation", body: "Dear Rahul" });
  });

  it("says which placeholder had no value for this recipient (QA-02)", async () => {
    const emailTemplate = { ...template, id: "t2", channel: "email", kind: "interview_confirmation", name: "Interview confirmation", subject: "Interview – {company}" };
    serve((url) => {
      if (url.includes("/templates")) return res(page([emailTemplate]));
      if (url.includes("/render")) return res({ template: emailTemplate, subject: "Interview – ", body: "Your interview with  is confirmed.", missing: ["company"] });
      return res(page([]));
    });
    render(<RecruiterMessages source={{ kind: "candidate", party: { kind: "candidate", id: "c1", name: "Rahul", whatsappTo: null, email: "r@x.test" } }} canWrite />);
    fireEvent.click(await screen.findByRole("button", { name: "Send email" }));
    fireEvent.change(await screen.findByLabelText("Template"), { target: { value: "t2" } });
    expect(await screen.findByText("Check the text: {company} has no value for this recipient.")).toBeTruthy();
    expect((screen.getByLabelText("Subject") as HTMLInputElement).value).toBe("Interview – ");
  });

  it("disables email with its reason for a candidate with no email (edge case)", async () => {
    serve(() => res(page([])));
    render(<RecruiterMessages source={{ kind: "candidate", party: { kind: "candidate", id: "c1", name: "Rahul", whatsappTo: "919876543210", email: null } }} canWrite />);
    expect(await screen.findByText("No messages sent yet.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Send email" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("No email address for Rahul.")).toBeTruthy();
  });

  it("is read only without the right, and a failed list read offers Retry", async () => {
    let fail = true;
    serve(() => (fail ? res({ detail: "boom" }, 500) : res(page([sent()]))));
    render(<RecruiterMessages source={{ kind: "company", companyId: "co1" }} canWrite={false} />);
    expect(await screen.findByText("Unable to load the messages.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Send WhatsApp" })).toBeNull();
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(/To Priya/)).toBeTruthy();
  });

  it("keeps what was typed when the API refuses the send", async () => {
    serve((url) => (url.includes("/templates") ? res(page([])) : res(page([]))), () => res({ detail: "This contact is inactive. Reactivate it before sending a message" }, 409));
    render(<RecruiterMessages source={{ kind: "candidate", party: { kind: "candidate", id: "c1", name: "Rahul", whatsappTo: null, email: "r@x.test" } }} canWrite />);
    fireEvent.click(await screen.findByRole("button", { name: "Send email" }));
    fireEvent.change(await screen.findByLabelText("Subject"), { target: { value: "Hi" } });
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Body" } });
    fireEvent.click(screen.getByRole("button", { name: "Send email" }));
    expect(await screen.findByText(/Reactivate it before sending/)).toBeTruthy();
    expect((screen.getByLabelText("Message") as HTMLTextAreaElement).value).toBe("Body");
  });
});
