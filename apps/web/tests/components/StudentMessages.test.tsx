import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StudentMessages from "@/components/StudentMessages";
import type { StudentMessage } from "@/lib/counselorMessages";

// ccrm-037 (DEC-SCOPE-273, MT4-MT9): the Messages card on the student 360 -- sends about one of the counselor's applications, replies
// recorded by hand, the log with direction and application, and the Overseas Admin's read-only view.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pageOf = (items: unknown[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const message = (over: Partial<StudentMessage> = {}): StudentMessage => ({
  id: "M1", student_id: "S1", application: { id: "A1", label: "Leeds · REF-37" }, direction: "outbound", channel: "whatsapp",
  template: { id: "T1", name: "Offer update" }, subject: null, body: "Your offer is in", delivery_status: null, sent_at: "2026-10-08T05:30:00Z",
  sender: { id: "c1", full_name: "Nora Counselor" }, ...over,
});
const recipient = { name: "Priya Student", email: "priya@example.com", whatsapp_to: "919876543210" };
const applications = [{ id: "A1", label: "Leeds · REF-37" }];

let items: StudentMessage[];
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  items = [message(), message({ id: "M2", direction: "inbound", channel: "email", subject: "Re: offer", body: "I accept", template: null, application: null })];
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST" && url.endsWith("/replies")) return Promise.resolve(res(message({ id: "M3", direction: "inbound" }), 201));
    if (init?.method === "POST") return Promise.resolve(res(message({ id: "M4" }), 201));
    if (url.includes("/templates")) return Promise.resolve(res(pageOf([{ id: "T1", name: "Offer update" }])));
    if (url.includes("/render")) return Promise.resolve(res({ template: { id: "T1", name: "Offer update", channel: "whatsapp" }, subject: null, body: "Hi Priya Student", missing: [] }));
    return Promise.resolve(res(pageOf(items)));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const posts = () => fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");

describe("StudentMessages (ccrm-037)", () => {
  it("lists sent messages and recorded replies with the application they are about (MT9)", async () => {
    render(<StudentMessages studentId="S1" recipient={recipient} applications={applications} canWrite />);
    const [sent, reply] = within(await screen.findByRole("list", { name: "Messages" })).getAllByRole("listitem");
    expect(sent.textContent).toContain("WhatsApp sent");
    expect(sent.textContent).toContain("About Leeds · REF-37");
    expect(sent.textContent).toContain("Offer update · Nora Counselor");
    expect(reply.textContent).toContain("Email reply received");
    expect(reply.textContent).toContain("Recorded by Nora Counselor");
    expect(reply.textContent).toContain("Re: offer");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/counselor/students/S1/messages?limit=50");
  });

  it("renders and sends a WhatsApp about the chosen application", async () => {
    vi.spyOn(window, "open").mockImplementation(() => null);
    render(<StudentMessages studentId="S1" recipient={recipient} applications={applications} canWrite />);
    await screen.findByRole("list", { name: "Messages" });
    fireEvent.change(screen.getByLabelText("About"), { target: { value: "A1" } });
    fireEvent.click(await screen.findByRole("button", { name: "Send WhatsApp" }));
    const composer = await screen.findByRole("group", { name: "WhatsApp message" });
    await within(composer).findByRole("option", { name: "Offer update" });
    fireEvent.change(within(composer).getByLabelText("Template"), { target: { value: "T1" } });
    await waitFor(() => expect((within(composer).getByLabelText("Message") as HTMLTextAreaElement).value).toBe("Hi Priya Student"));
    expect(fetchMock.mock.calls.some(([url]) => url === "/api/v1/counselor/students/S1/messages/render?template_id=T1&application_id=A1")).toBe(true);
    fireEvent.click(within(composer).getByRole("link", { name: /Open WhatsApp/ }));
    fireEvent.click(within(composer).getByRole("button", { name: "Yes, record as sent" }));
    expect(await screen.findByText("WhatsApp to Priya Student recorded.")).toBeTruthy();
    const [url, init] = posts()[0];
    expect(url).toBe("/api/v1/counselor/students/S1/messages");
    expect(JSON.parse(init.body)).toEqual({ application_id: "A1", channel: "whatsapp", template_id: "T1", body: "Hi Priya Student" });
  });

  it("records a reply by hand and re-reads the log (MT7)", async () => {
    render(<StudentMessages studentId="S1" recipient={recipient} applications={applications} canWrite />);
    await screen.findByRole("list", { name: "Messages" });
    fireEvent.click(screen.getByRole("button", { name: "Record a reply" }));
    const form = screen.getByRole("form", { name: "Record a reply" });
    fireEvent.change(within(form).getByLabelText("Channel"), { target: { value: "email" } });
    fireEvent.change(within(form).getByLabelText("Subject (optional)"), { target: { value: "Re: offer" } });
    fireEvent.change(within(form).getByLabelText("Reply"), { target: { value: "  I accept  " } });
    const listCalls = fetchMock.mock.calls.length;
    fireEvent.click(within(form).getByRole("button", { name: "Save reply" }));
    fireEvent.click(within(form).getByRole("button", { name: /Sav/ })); // a second click while saving sends nothing more
    expect(await screen.findByText("Reply recorded.")).toBeTruthy();
    expect(posts()).toHaveLength(1);
    const [url, init] = posts()[0];
    expect(url).toBe("/api/v1/counselor/students/S1/replies");
    expect(JSON.parse(init.body)).toEqual({ channel: "email", subject: "Re: offer", body: "I accept" });
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(listCalls + 1)); // the list re-read
    expect(screen.queryByRole("form", { name: "Record a reply" })).toBeNull();
  });

  it("shows the API's sentence when a reply is refused and keeps the text", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "POST" ? res({ detail: "Replies can be recorded up to 7 days back" }, 422) : res(pageOf([]))));
    render(<StudentMessages studentId="S1" recipient={recipient} applications={[]} canWrite />);
    expect(await screen.findByText("No messages sent yet.")).toBeTruthy();
    expect(screen.queryByLabelText("About")).toBeNull(); // no application of theirs: every message is general
    fireEvent.click(screen.getByRole("button", { name: "Record a reply" }));
    const form = screen.getByRole("form", { name: "Record a reply" });
    fireEvent.change(within(form).getByLabelText("Reply"), { target: { value: "Thanks" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save reply" }));
    expect((await within(form).findByRole("alert")).textContent).toContain("Replies can be recorded up to 7 days back");
    expect((within(form).getByLabelText("Reply") as HTMLTextAreaElement).value).toBe("Thanks");
  });

  it("disables WhatsApp with the reason when the student has no usable number", async () => {
    render(<StudentMessages studentId="S1" recipient={{ ...recipient, whatsapp_to: null }} applications={applications} canWrite />);
    await screen.findByRole("list", { name: "Messages" });
    expect((screen.getByRole("button", { name: "Send WhatsApp" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("No usable mobile number for Priya Student.")).toBeTruthy();
  });

  it("is read-only for the Overseas Admin (MT4)", async () => {
    render(<StudentMessages studentId="S1" recipient={recipient} applications={applications} canWrite={false} />);
    await screen.findByRole("list", { name: "Messages" });
    expect(screen.queryByRole("button", { name: "Send WhatsApp" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Record a reply" })).toBeNull();
    expect(screen.queryByLabelText("About")).toBeNull();
  });
});
