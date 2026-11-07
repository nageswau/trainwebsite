// pob-008 (DEC-SCOPE-423 B5-B9): the Team Lead's cadence library, and starting / showing / stopping a cadence on a contact message.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RecruiterCadenceLibrary from "@/components/RecruiterCadenceLibrary";
import RecruiterMessages from "@/components/RecruiterMessages";
import { stepsError, stepsSummary } from "@/lib/recruiterCadences";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const page = (items: unknown[]) => ({ items, total: items.length, limit: 100, offset: 0 });
const cadence = {
  id: "c1", name: "Intro", description: "Three touches", active: true, updated_at: "2026-11-07T05:00:00Z", can_edit: true,
  steps: [{ day: 0, channel: "email", template: null }, { day: 3, channel: "linkedin", template: null }, { day: 7, channel: "call", template: { id: "t9", name: "Call script" } }],
};
const contact = { id: "k1", name: "Priya", active: true, status: "contacted", mobile: "98765 43210", email: "k1@abc.example.com", whatsapp_to: "919876543210" };
const message = {
  id: "m1", kind: "contact", company_id: "co1", contact: { id: "k1", name: "Priya" }, candidate: null, channel: "linkedin", linkedin_action: "message",
  template: null, subject: null, body: "Hi", delivery_status: null, sent_at: "2026-10-08T05:05:00Z", sender: { id: "u1", full_name: "Asha" }, outcome: null,
  follow_up: null, replied_at: null, cadence: null,
};
const run = { id: "r1", cadence_id: "c1", name: "Intro", status: "active", step: 1, steps: 3, next_step_at: "2026-10-11T05:05:00Z", end_reason: null, ended_at: null, can_stop: true };

type Call = { url: string; method: string; body: unknown };
function serve(route: (url: string, method: string) => Response | undefined) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ url: String(url), method, body: init?.body ? JSON.parse(String(init.body)) : null });
    return Promise.resolve(route(String(url), method) ?? res(page([])));
  }));
  return calls;
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("cadence step rules", () => {
  it("mirrors the API's rules and summarises steps", () => {
    expect(stepsError([{ day: "0" }, { day: "3" }])).toBeNull();
    expect(stepsError([{ day: "1" }, { day: "3" }])).toMatch(/day 0/);
    expect(stepsError([{ day: "0" }, { day: "0" }])).toMatch(/later day/);
    expect(stepsError([{ day: "0" }])).toMatch(/2 to 10/);
    expect(stepsError([{ day: "0" }, { day: "91" }])).toMatch(/0 to 90/);
    expect(stepsSummary(cadence.steps)).toBe("Day 0 Email → Day 3 LinkedIn → Day 7 Call");
  });
});

describe("cadence library", () => {
  it("lists cadences and adds one with its steps", async () => {
    const calls = serve((url, method) => {
      if (url.includes("/templates")) return res(page([{ id: "t1", name: "Intro mail", channel: "email" }, { id: "t2", name: "LI note", channel: "linkedin" }]));
      if (method === "POST") return res({ ...cadence, id: "c2" }, 201);
      if (url.includes("/cadences")) return res({ items: [cadence], can_edit: true });
    });
    render(<RecruiterCadenceLibrary />);
    expect(await screen.findByText("Day 0 Email → Day 3 LinkedIn → Day 7 Call")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Add cadence" }));
    fireEvent.click(screen.getByRole("button", { name: "Add cadence" }));
    expect(await screen.findByText("Enter a name")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Name (required)"), { target: { value: "Fast" } });
    await waitFor(() => expect(screen.getByRole("option", { name: "Intro mail" })).toBeTruthy());
    fireEvent.change(screen.getByLabelText("Step 1 template"), { target: { value: "t1" } });
    fireEvent.change(screen.getByLabelText("Step 2 day"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Add cadence" }));
    expect(await screen.findByText(/later day/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Step 2 day"), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Add cadence" }));
    await screen.findByText("Cadence added.");
    expect(calls.find((c) => c.method === "POST")).toMatchObject({
      url: "/api/v1/recruiter/cadences",
      body: { name: "Fast", description: null, steps: [{ day: 0, channel: "email", template_id: "t1" }, { day: 2, channel: "linkedin", template_id: null }] },
    });
  });

  it("places an API step error on the steps and shows read-only lists to others", async () => {
    serve((url, method) => {
      if (method === "PATCH") return res({ detail: [{ loc: ["body", "steps"], msg: "Step 3: choose an approved shared Call template" }] }, 422);
      if (url.includes("/cadences")) return res({ items: [cadence], can_edit: true });
    });
    render(<RecruiterCadenceLibrary />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Intro" }));
    fireEvent.click(screen.getByRole("button", { name: "Save cadence" }));
    expect(await screen.findByText("Step 3: choose an approved shared Call template")).toBeTruthy();
  });

  it("shows the empty and failed states", async () => {
    serve((url) => (url.includes("/cadences") ? res({ items: [], can_edit: false }) : undefined));
    render(<RecruiterCadenceLibrary />);
    expect(await screen.findByText("No cadences yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add cadence" })).toBeNull();
    cleanup();
    serve(() => res({ detail: "boom" }, 500));
    render(<RecruiterCadenceLibrary />);
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "The cadences could not be loaded. Refresh the page to try again.");
  });
});

describe("cadence on a contact message", () => {
  it("starts a cadence on a message", async () => {
    const calls = serve((url, method) => {
      if (method === "POST") return res({ ...message, cadence: run }, 201);
      if (url.includes("/contacts")) return res({ items: [contact], can_edit: true });
      if (url.includes("/cadences")) return res({ items: [cadence], can_edit: false });
      if (url.includes("/messages")) return res(page([message]));
    });
    render(<RecruiterMessages source={{ kind: "company", companyId: "co1" }} canWrite />);
    fireEvent.click(await screen.findByRole("button", { name: /Start cadence/ }));
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    expect(await screen.findByText("Choose a cadence")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Cadence"), { target: { value: "c1" } });
    expect(screen.getByText(/This message is step 1/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    await screen.findByText("Cadence started for Priya.");
    expect(calls.find((c) => c.method === "POST")).toMatchObject({ url: "/api/v1/recruiter/messages/m1/cadence", body: { cadence_id: "c1" } });
  });

  it("shows a running cadence with Stop, and an ended one without", async () => {
    const calls = serve((url, method) => {
      if (method === "POST") return res({ ...message, cadence: { ...run, status: "stopped", end_reason: "manual", can_stop: false } });
      if (url.includes("/contacts")) return res({ items: [contact], can_edit: true });
      if (url.includes("/cadences")) return res({ items: [cadence], can_edit: false });
      if (url.includes("/messages")) return res(page([{ ...message, cadence: run }, { ...message, id: "m2", cadence: { ...run, id: "r2", status: "replied", end_reason: "reply", can_stop: false } }]));
    });
    render(<RecruiterMessages source={{ kind: "company", companyId: "co1" }} canWrite />);
    // QA-01: the next step's time reads like the message line's own time (12-hour, IST)
    expect(await screen.findByText("Cadence: Intro · step 1 of 3 · next – 11 Oct 2026 – 10:35 AM")).toBeTruthy();
    expect(screen.getByText("Cadence Intro ended: the contact replied (step 1 of 3)")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Start cadence/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Stop cadence/ }));
    await screen.findByText("Cadence stopped.");
    expect(calls.find((c) => c.method === "POST")?.url).toBe("/api/v1/recruiter/messages/m1/cadence/stop");
  });
});
