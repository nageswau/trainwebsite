// pob-007 (DEC-SCOPE-422): LinkedIn logging and message outcomes in the Messages section, and LinkedIn rows in the timeline.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RecruiterMessages from "@/components/RecruiterMessages";
import { type RecTimelineRow, timelineEntry } from "@/lib/recruiterTimeline";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const page = (items: unknown[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const contact = { id: "k1", name: "Priya", active: true, mobile: "98765 43210", email: "k1@abc.example.com", whatsapp_to: "919876543210" };
const linkedin = {
  id: "m1", kind: "contact", company_id: "co1", contact: { id: "k1", name: "Priya" }, candidate: null, channel: "linkedin", linkedin_action: "connection_request",
  template: null, subject: null, body: "", delivery_status: null, sent_at: "2026-10-08T05:05:00Z", sender: { id: "u1", full_name: "Asha" }, outcome: null,
  follow_up: null, replied_at: null,
};

type Call = { url: string; init?: RequestInit };
function serve(messages: unknown[]) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    if (init?.method === "POST") return Promise.resolve(res(linkedin, 201));
    if (String(url).includes("/contacts")) return Promise.resolve(res({ items: [contact], can_edit: true }));
    if (String(url).includes("/templates")) return Promise.resolve(res(page([])));
    return Promise.resolve(res(page(messages)));
  }));
  return calls;
}
const posted = (calls: Call[]) => calls.filter((c) => c.init?.method === "POST").map((c) => ({ url: c.url, body: JSON.parse(String(c.init?.body)) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("pob-007 BD activity", () => {
  it("logs a LinkedIn connection request without a template and reloads the list", async () => {
    const calls = serve([]);
    render(<RecruiterMessages source={{ kind: "company", companyId: "co1" }} canWrite />);
    fireEvent.click(await screen.findByRole("button", { name: "LinkedIn message" }));
    fireEvent.click(await screen.findByRole("button", { name: "Log as sent" }));
    await screen.findByText("LinkedIn connection request to Priya logged.");
    expect(posted(calls)).toEqual([{ url: "/api/v1/recruiter/messages/linkedin", body: { contact_id: "k1", action: "connection_request", template_id: null, body: "" } }]);
  });

  it("needs the text for a LinkedIn message", async () => {
    serve([]);
    render(<RecruiterMessages source={{ kind: "company", companyId: "co1" }} canWrite />);
    fireEvent.click(await screen.findByRole("button", { name: "LinkedIn message" }));
    fireEvent.change(await screen.findByLabelText("What did you send on LinkedIn?"), { target: { value: "message" } });
    expect((screen.getByRole("button", { name: "Log as sent" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Message sent"), { target: { value: "Hello Priya" } });
    expect((screen.getByRole("button", { name: "Log as sent" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("shows a LinkedIn line and records its outcome with a next follow-up", async () => {
    const calls = serve([linkedin]);
    render(<RecruiterMessages source={{ kind: "company", companyId: "co1" }} canWrite />);
    expect(await screen.findByText(/LinkedIn connection request sent/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Record outcome/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save outcome" }));
    expect(await screen.findByText("Describe the outcome")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Outcome (required)"), { target: { value: "Accepted" } });
    fireEvent.change(screen.getByLabelText("Next follow-up due (IST, optional)"), { target: { value: "2030-01-02T10:00" } });
    fireEvent.change(screen.getByLabelText("Follow-up reason"), { target: { value: "jd" } });
    fireEvent.click(screen.getByRole("button", { name: "Save outcome" }));
    await screen.findByText("Outcome saved and follow-up added.");
    expect(posted(calls)[0]).toEqual({
      url: "/api/v1/recruiter/messages/m1/outcome", body: { outcome: "Accepted", next_follow_up: { due_at: "2030-01-02T10:00:00+05:30", reason: "jd" } },
    });
  });

  it("reads LinkedIn rows in the timeline", () => {
    const row = {
      id: "r1", kind: "message", at: "2026-10-08T05:05:00Z", actor: null, event: "linkedin", from_value: "", from_label: "", to_value: "", to_label: "Priya",
      subject: null, status: "message", reason: null, context: null, duration_seconds: null, scheduled_for: null,
    } as RecTimelineRow;
    const described = timelineEntry(row);
    expect(described.badge).toBe("LinkedIn");
    expect(described.title).toBe("LinkedIn message sent");
  });
});
