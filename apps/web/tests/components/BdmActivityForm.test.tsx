import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmActivityForm from "@/components/BdmActivityForm";
import type { Activity } from "@/lib/bdmActivities";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const saved = (over: Partial<Activity> = {}): Activity => ({
  id: "a1", organization: { id: "o1", code: "ORG-000001", name: "St Mary", org_type: "college" }, bdm: { id: "b1", full_name: "Asha" },
  contact_id: null, contact_name: null, contact_removed: false, channel: "call", direction: "outbound", occurred_at: "2026-10-03T05:00:00Z",
  note: null, created_at: "2026-10-03T05:00:00Z", updated_at: "2026-10-03T05:00:00Z", permissions: { can_change: true }, ...over,
});
const contacts = [{ id: "c1", name: "Dr Rao" }, { id: "c2", name: "Ms Iyer" }];
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmActivityForm (bdm-009 §6.3)", () => {
  it("shows direction only for call, WhatsApp and email and clears it on a channel change", () => {
    render(<BdmActivityForm organizationId="o1" contacts={contacts} onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole("group", { name: "Direction (required)" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Channel (required)"), { target: { value: "visit" } });
    expect(screen.queryByRole("group", { name: /Direction/ })).toBeNull();
  });

  it("clears the direction when the channel changes", () => {
    render(<BdmActivityForm organizationId="o1" contacts={contacts} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Outgoing"));
    fireEvent.change(screen.getByLabelText("Channel (required)"), { target: { value: "visit" } });
    fireEvent.change(screen.getByLabelText("Channel (required)"), { target: { value: "call" } });
    expect(screen.getByLabelText("Outgoing")).not.toBeChecked();
    expect(screen.getByLabelText("Incoming")).not.toBeChecked();
  });

  it("logs a call with the picked contact and a UTC time", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res(saved({ contact_id: "c2", contact_name: "Ms Iyer" }), 201)));
    vi.stubGlobal("fetch", fetchMock);
    const onSaved = vi.fn();
    render(<BdmActivityForm organizationId="o1" contacts={contacts} onSaved={onSaved} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Outgoing"));
    fireEvent.change(screen.getByLabelText("Contact"), { target: { value: "c2" } });
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: "Asked about the MoU" } });
    fireEvent.click(screen.getByRole("button", { name: "Save activity" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ id: "a1" }), true));
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/bdm/activities");
    const body = JSON.parse(String(init.body));
    expect(body).toMatchObject({ organization_id: "o1", channel: "call", direction: "outbound", contact_id: "c2", note: "Asked about the MoU" });
    expect(body.occurred_at).toMatch(/Z$/);
  });

  it("asks for a direction before sending and focuses it", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmActivityForm organizationId="o1" contacts={contacts} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save activity" }));
    expect(screen.getByText("Choose outgoing or incoming.")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Check the highlighted fields.");
    await waitFor(() => expect(screen.getByLabelText("Outgoing")).toHaveFocus());
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("focuses Channel on open and shows the time and privacy hints", async () => {
    render(<BdmActivityForm organizationId="o1" contacts={contacts} onSaved={vi.fn()} onCancel={vi.fn()} />);
    await waitFor(() => expect(screen.getByLabelText("Channel (required)")).toHaveFocus());
    expect(screen.getByLabelText("When (required)")).toHaveAccessibleDescription(/Your local time\. Up to 7 days back\./);
    expect(screen.getByLabelText("Note")).toHaveAccessibleDescription(/Everyone who can see this organization can read this note\./);
  });

  it("puts a time-rule 422 on the When field", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "When can't be in the future" }, 422))));
    render(<BdmActivityForm organizationId="o1" contacts={contacts} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Incoming"));
    fireEvent.click(screen.getByRole("button", { name: "Save activity" }));
    expect(await screen.findByText("When can't be in the future")).toHaveAttribute("id", expect.stringContaining("occurred_at"));
  });

  it("shows a refusal and keeps the entry", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Only the organization's assigned BDM can log activity" }, 403))));
    render(<BdmActivityForm organizationId="o1" contacts={contacts} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Outgoing"));
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: "keep me" } });
    fireEvent.click(screen.getByRole("button", { name: "Save activity" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only the organization's assigned BDM can log activity");
    expect(screen.getByLabelText("Note")).toHaveValue("keep me");
  });

  it("edits only the changed fields and sends direction null when the channel no longer needs one", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res(saved({ channel: "visit", direction: null }))));
    vi.stubGlobal("fetch", fetchMock);
    const onSaved = vi.fn();
    render(<BdmActivityForm organizationId="o1" contacts={contacts} activity={saved()} onSaved={onSaved} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Channel (required)"), { target: { value: "visit" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ channel: "visit" }), false));
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect([url, init.method]).toEqual(["/api/v1/bdm/activities/a1", "PATCH"]);
    expect(JSON.parse(String(init.body))).toEqual({ channel: "visit", direction: null });
  });

  it("loads the organization's contacts when it is picked (activities page)", async () => {
    const fetchMock = vi.fn((url: string) =>
      Promise.resolve(url.includes("?") ? res({ items: [{ id: "o9", code: "ORG-000009", name: "St Jude", city: "Kochi" }], total: 1 }) : res({ organization: { id: "o9", contacts } })),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmActivityForm onSaved={vi.fn()} onCancel={vi.fn()} />);
    const picker = screen.getByRole("combobox", { name: /Organization/ });
    fireEvent.focus(picker);
    fireEvent.change(picker, { target: { value: "Jude" } });
    fireEvent.click(await screen.findByRole("option", { name: /St Jude/ }));
    await waitFor(() => expect(screen.getByRole("option", { name: "Ms Iyer" })).toBeInTheDocument());
  });

  it("clears the contact options as soon as the organization is cleared", async () => {
    const fetchMock = vi.fn((url: string) =>
      Promise.resolve(url.includes("?") ? res({ items: [{ id: "o9", code: "ORG-000009", name: "St Jude", city: "Kochi" }], total: 1 }) : res({ organization: { id: "o9", contacts } })),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmActivityForm onSaved={vi.fn()} onCancel={vi.fn()} />);
    const picker = screen.getByRole("combobox", { name: /Organization/ });
    fireEvent.focus(picker);
    fireEvent.change(picker, { target: { value: "Jude" } });
    fireEvent.click(await screen.findByRole("option", { name: /St Jude/ }));
    await waitFor(() => expect(screen.getByRole("option", { name: "Ms Iyer" })).toBeInTheDocument());
    fireEvent.change(picker, { target: { value: "" } });
    expect(screen.queryByRole("option", { name: "Ms Iyer" })).toBeNull();
  });

  it("hands a refusal on an edit to onRefused instead of keeping the form editable", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Only today's activities can be changed" }, 409))));
    const onRefused = vi.fn();
    render(<BdmActivityForm organizationId="o1" contacts={contacts} activity={saved()} onSaved={vi.fn()} onCancel={vi.fn()} onRefused={onRefused} />);
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(onRefused).toHaveBeenCalledWith(409, "Only today's activities can be changed"));
  });
});
