import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LeadMessages from "@/components/LeadMessages";
import type { LeadMessage } from "@/lib/telecallerMessages";
import { message } from "@/tests/helpers/messages";

// tel-013 (spec §4): the lead's messages -- the send log, Send WhatsApp with its composer (template render, edit, wa.me, confirm) and delete.
const res = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status });
const pageOf = (items: unknown[]) => ({ items, total: items.length, limit: 100, offset: 0 });
const TEMPLATE = { id: "T1", channel: "whatsapp", kind: "brochure", name: "Send Cyber Security Brochure", product: null, asset: null, subject: null, body: "x", active: true };

let items: LeadMessage[];
let rendered: Record<string, unknown>;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  items = [message(), message({ id: "M2", template: null, body: "Free text", can_delete: false })];
  rendered = { template: { id: "T1", name: TEMPLATE.name, channel: "whatsapp", kind: "brochure" }, subject: null, body: "Hi Priya Sharma, see the brochure",
    brochure_link: null, product_mismatch: false };
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") return Promise.resolve(res(message({ id: "M3" }), 201));
    if (init?.method === "DELETE") return Promise.resolve(res(null, 204));
    if (url.startsWith("/api/v1/telecaller/leads/L1/messages")) return Promise.resolve(res(pageOf(items)));
    if (url.startsWith("/api/v1/telecaller/templates")) return Promise.resolve(res(pageOf([TEMPLATE])));
    if (url.startsWith("/api/v1/telecaller/leads/L1/render")) return Promise.resolve(res(rendered));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const sent = (method: string) => {
  const found = fetchMock.mock.calls.find(([, i]) => i?.method === method);
  return found ? { url: found[0] as string, body: JSON.parse((found[1] as RequestInit).body as string || "null") } : null;
};

const onChanged = vi.fn(); // tel-015: the page's timeline re-reads after a send or delete
async function openComposer() {
  onChanged.mockClear();
  render(<LeadMessages leadId="L1" whatsappTo="919876543210" canWrite openSignal={0} onChanged={onChanged} />);
  fireEvent.click(await screen.findByRole("button", { name: "Send WhatsApp" }));
  await screen.findByRole("option", { name: TEMPLATE.name });
}

describe("LeadMessages (tel-013)", () => {
  it("lists the sends with the AC2 line, the template or Custom message, the sender and the text; only deletable ones offer Delete", async () => {
    render(<LeadMessages leadId="L1" whatsappTo="919876543210" canWrite openSignal={0} />);
    const list = await screen.findByRole("list", { name: "Messages" });
    const [first, second] = within(list).getAllByRole("listitem");
    expect(first.textContent).toContain("WhatsApp sent – 13 Sept 2026 – 10:35 AM");
    expect(first.textContent).toContain("Send Cyber Security Brochure");
    expect(first.textContent).toContain("Tara Caller");
    expect(first.textContent).toContain("Hi Priya, here is the brochure");
    expect(within(first).getByRole("button", { name: "Delete" })).toBeTruthy();
    expect(second.textContent).toContain("Custom message");
    expect(within(second).queryByRole("button")).toBeNull();
  });

  it("shows the empty state, and no Send WhatsApp when the viewer can't write", async () => {
    items = [];
    render(<LeadMessages leadId="L1" whatsappTo="919876543210" canWrite={false} openSignal={0} />);
    expect(await screen.findByText("No messages sent yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Send WhatsApp" })).toBeNull();
  });

  it("disables Send WhatsApp with the reason when the lead has no number (AC3)", async () => {
    render(<LeadMessages leadId="L1" whatsappTo={null} canWrite openSignal={0} />);
    const button = await screen.findByRole("button", { name: "Send WhatsApp" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(button.getAttribute("aria-describedby")).toBeTruthy();
    expect(screen.getByText("No WhatsApp or mobile number on this lead.")).toBeTruthy();
  });

  it("renders a chosen template into editable text and opens wa.me with the edited text (AC1)", async () => {
    await openComposer();
    fireEvent.change(screen.getByLabelText("Template"), { target: { value: "T1" } });
    const text = await screen.findByDisplayValue("Hi Priya Sharma, see the brochure");
    expect(fetchMock.mock.calls.some(([u]) => String(u) === "/api/v1/telecaller/leads/L1/render?template_id=T1")).toBe(true);
    fireEvent.change(text, { target: { value: "Hi Priya & family" } });
    const link = screen.getByRole("link", { name: /Open WhatsApp/ });
    expect(link.getAttribute("href")).toBe("https://wa.me/919876543210?text=Hi%20Priya%20%26%20family");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("warns, but still allows, another product's template", async () => {
    rendered = { ...rendered, product_mismatch: true };
    await openComposer();
    fireEvent.change(screen.getByLabelText("Template"), { target: { value: "T1" } });
    expect(await screen.findByText(/made for another product/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Open WhatsApp/ })).toBeTruthy();
  });

  it("records the send only after the telecaller confirms it (AC2) and reloads the list", async () => {
    await openComposer();
    fireEvent.change(screen.getByLabelText("Template"), { target: { value: "T1" } });
    await screen.findByDisplayValue("Hi Priya Sharma, see the brochure");
    fireEvent.click(screen.getByRole("link", { name: /Open WhatsApp/ }));
    expect(sent("POST")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Yes, record as sent" }));
    await screen.findByText("WhatsApp send recorded.");
    expect(onChanged).toHaveBeenCalledTimes(1);
    expect(sent("POST")).toEqual({ url: "/api/v1/telecaller/leads/L1/messages",
      body: { channel: "whatsapp", template_id: "T1", body: "Hi Priya Sharma, see the brochure" } });
    await waitFor(() => expect(fetchMock.mock.calls.filter(([u]) => String(u).startsWith("/api/v1/telecaller/leads/L1/messages?")).length).toBe(2));
    expect(screen.queryByLabelText("Message")).toBeNull();
  });

  it("logs nothing when the telecaller says it was not sent, and keeps the text (edge case)", async () => {
    await openComposer();
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "My own words" } });
    fireEvent.click(screen.getByRole("link", { name: /Open WhatsApp/ }));
    fireEvent.click(screen.getByRole("button", { name: "Not sent" }));
    expect(sent("POST")).toBeNull();
    expect(screen.getByDisplayValue("My own words")).toBeTruthy();
  });

  it("sends a custom message without a template, and offers no link for empty text", async () => {
    await openComposer();
    expect(screen.queryByRole("link", { name: /Open WhatsApp/ })).toBeNull();
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "  Hello  " } });
    fireEvent.click(screen.getByRole("link", { name: /Open WhatsApp/ }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, record as sent" }));
    await screen.findByText("WhatsApp send recorded.");
    expect(sent("POST")?.body).toEqual({ channel: "whatsapp", body: "Hello" });
  });

  it("shows a refused send in place and keeps the composer", async () => {
    fetchMock.mockImplementationOnce(() => Promise.resolve(res(pageOf(items))));
    await openComposer();
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "POST" ? res({ detail: "This lead is closed. A manager can reopen it before a message is sent" }, 409) : res(pageOf([]))));
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("link", { name: /Open WhatsApp/ }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, record as sent" }));
    expect(await screen.findByText(/This lead is closed/)).toBeTruthy();
    expect(screen.getByDisplayValue("Hello")).toBeTruthy();
  });

  it("records one send however quickly the confirm is activated twice (QA-03)", async () => {
    await openComposer();
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("link", { name: /Open WhatsApp/ }));
    const yes = screen.getByRole("button", { name: "Yes, record as sent" });
    act(() => {
      yes.click();
      yes.click();
    });
    await screen.findByText("WhatsApp send recorded.");
    expect(fetchMock.mock.calls.filter(([, i]) => i?.method === "POST")).toHaveLength(1);
  });

  it("styles another product's template as a warning (QA-01)", async () => {
    rendered = { ...rendered, product_mismatch: true };
    await openComposer();
    fireEvent.change(screen.getByLabelText("Template"), { target: { value: "T1" } });
    expect((await screen.findByText(/made for another product/)).className).toBe("form-warning");
  });

  it("moves focus into the composer when it opens and back to Send WhatsApp when it closes (QA-02, QA-04)", async () => {
    await openComposer();
    expect(document.activeElement).toBe(screen.getByLabelText("Template"));
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("link", { name: /Open WhatsApp/ }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, record as sent" }));
    await screen.findByText("WhatsApp send recorded.");
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Send WhatsApp" }));
  });

  it("deletes a send after confirming", async () => {
    render(<LeadMessages leadId="L1" whatsappTo="919876543210" canWrite openSignal={0} />);
    const list = await screen.findByRole("list", { name: "Messages" });
    fireEvent.click(within(list).getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await screen.findByText("Message deleted.");
    expect(sent("DELETE")?.url).toBe("/api/v1/telecaller/messages/M1");
  });

  it("opens the composer when the page's WhatsApp button is pressed", async () => {
    const { rerender } = render(<LeadMessages leadId="L1" whatsappTo="919876543210" canWrite openSignal={0} />);
    await screen.findByRole("list", { name: "Messages" });
    rerender(<LeadMessages leadId="L1" whatsappTo="919876543210" canWrite openSignal={1} />);
    expect(await screen.findByLabelText("Message")).toBeTruthy();
  });
});
