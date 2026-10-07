import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LeadMessages from "@/components/LeadMessages";
import type { LeadMessage } from "@/lib/telecallerMessages";
import { emailMessage, message } from "@/tests/helpers/messages";

// tel-014 (DEC-SCOPE-106, spec §5): Send email from the lead's Messages -- the composer (template render, subject, body, send) and the
// email rows with their delivery status.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pageOf = (items: unknown[]) => ({ items, total: items.length, limit: 100, offset: 0 });
const TEMPLATE = { id: "TE", channel: "email", kind: "course_brochure", name: "Course brochure", product: null, asset: null, subject: "s", body: "b", active: true };

let items: LeadMessage[];
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  items = [emailMessage({ delivery_status: "failed" }), message()];
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") return Promise.resolve(res(emailMessage({ id: "E2", delivery_status: "queued" }), 201));
    if (url.startsWith("/api/v1/telecaller/leads/L1/messages")) return Promise.resolve(res(pageOf(items)));
    if (url.startsWith("/api/v1/telecaller/templates")) return Promise.resolve(res(pageOf([TEMPLATE])));
    if (url.startsWith("/api/v1/telecaller/leads/L1/render")) {
      return Promise.resolve(res({ template: { id: "TE", name: TEMPLATE.name, channel: "email", kind: "course_brochure" }, subject: "Python for Priya Sharma",
        body: "Dear Priya Sharma, the brochure: https://x.test/b", brochure_link: null, product_mismatch: false }));
    }
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const posts = () => fetchMock.mock.calls.filter(([, i]) => i?.method === "POST").map(([u, i]) => ({ url: u, body: JSON.parse((i as RequestInit).body as string) }));
const listLoads = () => fetchMock.mock.calls.filter(([u, i]) => !i?.method && String(u).startsWith("/api/v1/telecaller/leads/L1/messages?")).length;

async function openComposer() {
  render(<LeadMessages leadId="L1" whatsappTo="919876543210" email="priya@example.com" canWrite openSignal={0} />);
  fireEvent.click(await screen.findByRole("button", { name: "Send email" }));
  await screen.findByRole("option", { name: TEMPLATE.name });
}

describe("LeadMessages email (tel-014)", () => {
  it("shows an email row's subject and delivery status; a failed one says so and offers no Delete (AC2, EM2)", async () => {
    render(<LeadMessages leadId="L1" whatsappTo="919876543210" email="priya@example.com" canWrite openSignal={0} />);
    const [failed] = within(await screen.findByRole("list", { name: "Messages" })).getAllByRole("listitem");
    expect(failed.textContent).toContain("Email failed – 13 Sept 2026 – 10:35 AM");
    expect(failed.textContent).toContain("Your Python brochure");
    expect(within(failed).getByText(/was not delivered/)).toBeTruthy();
    expect(within(failed).queryByRole("button")).toBeNull();
  });

  it("disables Send email with the reason when the lead has no email address (AC3)", async () => {
    render(<LeadMessages leadId="L1" whatsappTo="919876543210" email={null} canWrite openSignal={0} />);
    const button = await screen.findByRole("button", { name: "Send email" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(button.getAttribute("aria-describedby")).toBeTruthy();
    expect(screen.getByText("No email address on this lead.")).toBeTruthy();
  });

  it("offers no Send email to a viewer who can't write", async () => {
    render(<LeadMessages leadId="L1" whatsappTo="919876543210" email="priya@example.com" canWrite={false} openSignal={0} />);
    await screen.findByRole("list", { name: "Messages" });
    expect(screen.queryByRole("button", { name: "Send email" })).toBeNull();
  });

  it("renders a template into an editable subject and body and sends the edited email (AC1)", async () => {
    await openComposer();
    expect(document.activeElement).toBe(screen.getByLabelText("Template"));
    fireEvent.change(screen.getByLabelText("Template"), { target: { value: "TE" } });
    const subject = await screen.findByDisplayValue("Python for Priya Sharma");
    expect(screen.getByLabelText("Message")).toHaveProperty("value", "Dear Priya Sharma, the brochure: https://x.test/b");
    fireEvent.change(subject, { target: { value: "  Your Python course  " } });
    fireEvent.click(screen.getByRole("button", { name: "Send email" }));
    await screen.findByText("Email queued for sending.");
    expect(posts()).toEqual([{ url: "/api/v1/telecaller/leads/L1/messages",
      body: { channel: "email", template_id: "TE", subject: "Your Python course", body: "Dear Priya Sharma, the brochure: https://x.test/b" } }]);
    expect(screen.queryByLabelText("Subject")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Send email" }));
  });

  it("needs a subject and a message before it can send a custom email (EM4)", async () => {
    await openComposer();
    const send = screen.getByRole("button", { name: "Send email" }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Subject"), { target: { value: "Hello" } });
    expect(send.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Dear Priya" } });
    expect(send.disabled).toBe(false);
    fireEvent.click(send);
    await screen.findByText("Email queued for sending.");
    expect(posts()[0].body).toEqual({ channel: "email", subject: "Hello", body: "Dear Priya" });
  });

  it("shows a refusal (SMTP not set up) in place and keeps what was typed", async () => {
    await openComposer();
    fetchMock.mockImplementation((_url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "POST" ? res({ detail: "Email is not set up. Ask an administrator to configure SMTP." }, 503) : res(pageOf([]))));
    fireEvent.change(screen.getByLabelText("Subject"), { target: { value: "Hello" } });
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Dear Priya" } });
    fireEvent.click(screen.getByRole("button", { name: "Send email" }));
    expect(await screen.findByText(/Email is not set up/)).toBeTruthy();
    expect(screen.getByDisplayValue("Dear Priya")).toBeTruthy();
  });

  it("sends once however quickly Send email is activated twice", async () => {
    await openComposer();
    fireEvent.change(screen.getByLabelText("Subject"), { target: { value: "Hello" } });
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Dear Priya" } });
    const send = screen.getByRole("button", { name: "Send email" });
    act(() => {
      send.click();
      send.click();
    });
    await screen.findByText("Email queued for sending.");
    expect(posts()).toHaveLength(1);
  });

  it("refreshes the list while an email is still sending, and stops once none is", async () => {
    vi.useFakeTimers();
    const advance = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
    items = [emailMessage({ delivery_status: "queued" })];
    render(<LeadMessages leadId="L1" whatsappTo={null} email="priya@example.com" canWrite openSignal={0} />);
    await advance(0);
    expect(screen.getByText(/Email sending/)).toBeTruthy();
    items = [emailMessage({ delivery_status: "sent" })];
    await advance(4000);
    expect(listLoads()).toBe(1);
    await advance(1000);
    expect(screen.getByText(/Email sent/)).toBeTruthy();
    expect(listLoads()).toBe(2);
    await advance(15000);
    expect(listLoads()).toBe(2);
  });

  it("opens the email composer when the page's Email button is pressed", async () => {
    const { rerender } = render(<LeadMessages leadId="L1" whatsappTo={null} email="priya@example.com" canWrite openSignal={0} emailSignal={0} />);
    await screen.findByRole("list", { name: "Messages" });
    rerender(<LeadMessages leadId="L1" whatsappTo={null} email="priya@example.com" canWrite openSignal={0} emailSignal={1} />);
    expect(await screen.findByLabelText("Subject")).toBeTruthy();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText("Template")));
  });
});
