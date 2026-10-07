import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LeadDetailPanel from "@/components/LeadDetailPanel";
import type { TelecallerLeadDetail, TimelineRow } from "@/lib/telecallerLeads";

// tel-008 (spec §3, AC3/AC4, D1/D2/D4): the lead detail -- §2 fields, priority with the activity list, the contact edit, Call and the
// stage control; a handed-over lead is read-only.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pageOf = <T,>(items: T[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const detail = (over: Partial<TelecallerLeadDetail> = {}): TelecallerLeadDetail => ({
  id: "L1", lead_code: "LD-000042", name: "Asha Rao", email: "asha@example.com", phone: "+91 98765 43210", whatsapp_number: "9876543210",
  city: "Hyderabad", state: "Telangana", qualification: "B.Tech", passing_year: 2024, institution: "JNTU", division: "it", subject: "Python",
  status: "contacted", status_label: "Contacted", source: "instagram", priority: "warm", created_at: "2026-10-06T05:00:00Z",
  stage_changed_at: "2026-10-06T05:00:00Z", product: { id: "p1", name: "Cyber Security" }, campaign: { id: "c1", name: "Sep 2026" },
  telecaller: { id: "t1", full_name: "Tara Caller" }, counselor: null, read_only: false, message: "Please call after 6pm", whatsapp_to: "919876543210", ...over,
});
const priorityRow: TimelineRow = {
  id: "a1", kind: "priority", at: "2026-10-06T06:00:00Z", actor: { id: "t1", full_name: "Tara Caller" }, from_value: "warm", from_label: "Warm",
  to_value: "hot", to_label: "Hot", reason: null,
};
const products = pageOf([{ id: "p1", group: "it", name: "Cyber Security", team: "it", program: null, active: true, sort_order: 1 },
  { id: "p2", group: "it", name: "Java", team: "it", program: null, active: true, sort_order: 2 }]);

const script = { id: "s1", product: { id: "p1", name: "Cyber Security", group: "it", active: true }, name: "Cyber Security call", active: true,
  steps: [{ title: "Greet", notes: "Introduce yourself" }, { title: "Ask about background", notes: null }] };

// tel-009: the qualification section the panel reads on open (its own behaviour is LeadQualificationForm.test.tsx's)
const qual = {
  lead_id: "L1", product: { id: "p1", name: "Cyber Security", group: "it" }, product_group: "it", qualification: "B.Tech", passing_year: 2024,
  city: "Hyderabad", state: "Telangana", current_org: null, work_experience_years: null, it_skill_level: null, career_objective: null,
  preferred_batch: null, budget_range: null, preferred_mode: null, study_level: null, preferred_course: null, intake: null,
  academic_percentage: null, english_test_status: null, passport_status: null, read_only: false, updated_by: null, updated_at: null,
};

let fetchMock: ReturnType<typeof vi.fn>;
let patchReply: (body: Record<string, unknown>) => Response;
let timeline: TimelineRow[];
let scripts: () => Response;
const calls = (method: string) => fetchMock.mock.calls.filter(([, init]) => (init?.method ?? "GET") === method);
beforeEach(() => {
  timeline = [];
  scripts = () => res(pageOf([]));
  patchReply = (body) => res({ ...detail(), ...body });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.startsWith("/api/v1/telecaller/leads/L1/calls")) { // tel-010's section
      return Promise.resolve(init?.method === "POST" ? res({ call: { id: "C1", lead_id: "L1", occurred_at: "2026-10-07T05:30:00Z", duration_seconds: 60,
        call_type: "outgoing", outcome: "already_joined", outcome_label: "Already Joined Elsewhere", connected: true, remarks: null,
        caller: { id: "t1", full_name: "Tara Caller" }, created_at: "2026-10-07T05:31:00Z", can_change: true },
        lead: { id: "L1", status: "lost", status_label: "Lost" }, follow_up_id: null }, 201) : res(pageOf([])));
    }
    if (url.startsWith("/api/v1/telecaller/leads/L1/messages")) return Promise.resolve(res(pageOf([]))); // tel-013's section
    if (url.startsWith("/api/v1/telecaller/templates")) return Promise.resolve(res(pageOf([])));
    if (init?.method === "PATCH") return Promise.resolve(patchReply(JSON.parse(String(init.body))));
    if (init?.method === "POST") return Promise.resolve(res({ id: "L1", status: "qualified", status_label: "Qualified", stage_changed_at: "x" }));
    if (url.startsWith("/api/v1/telecaller/leads/L1/timeline")) return Promise.resolve(res(pageOf(timeline)));
    if (url.startsWith("/api/v1/telecaller/leads/L1/follow-ups")) return Promise.resolve(res(pageOf([]))); // tel-011's section
    if (url === "/api/v1/telecaller/leads/L1/appointments") return Promise.resolve(res({ items: [] })); // tel-016's section
    if (url.startsWith("/api/v1/telecaller/products")) return Promise.resolve(res(products));
    if (url.startsWith("/api/v1/telecaller/scripts")) return Promise.resolve(scripts());
    if (url === "/api/v1/telecaller/leads/L1/qualification") return Promise.resolve(res(init?.method === "PUT" ? { ...qual, ...JSON.parse(String(init.body)) } : qual));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LeadDetailPanel (tel-008)", () => {
  it("shows the follow-ups section, with Add only for the lead's telecaller on an open lead (tel-011)", async () => {
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen={false} />);
    expect(await screen.findByText("No follow-ups yet.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add follow-up" })).toBeTruthy();
    cleanup();
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen />); // a manager reads only (F2)
    expect(await screen.findByText("No follow-ups yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add follow-up" })).toBeNull();
    cleanup();
    render(<LeadDetailPanel initial={detail({ status: "lost", status_label: "Lost" })} timeline={pageOf([])} canReopen={false} />); // F4
    expect(await screen.findByText("No follow-ups yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add follow-up" })).toBeNull();
  });

  it("offers Log call only to the lead's telecaller on an open lead (tel-010 D8, CL2)", async () => {
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen={false} />);
    expect(await screen.findByText("No calls logged yet.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Log call" })).toBeTruthy();
    cleanup();
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen />);
    expect(await screen.findByText("No calls logged yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Log call" })).toBeNull();
    cleanup();
    render(<LeadDetailPanel initial={detail({ status: "lost", status_label: "Lost" })} timeline={pageOf([])} canReopen={false} />);
    expect(await screen.findByText("No calls logged yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Log call" })).toBeNull();
  });

  it("opens the call log from Call, and a closing outcome updates the stage and re-reads the follow-ups (tel-010)", async () => {
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen={false} />);
    await screen.findByText("No calls logged yet.");
    const link = screen.getByRole("link", { name: "Call Asha Rao" });
    link.addEventListener("click", (e) => e.preventDefault()); // jsdom can't follow tel:
    fireEvent.click(link);
    const form = screen.getByRole("form", { name: "Log call" });
    fireEvent.change(within(form).getByLabelText("Outcome (required)"), { target: { value: "already_joined" } });
    const followUpReads = () => fetchMock.mock.calls.filter(([u]) => String(u).startsWith("/api/v1/telecaller/leads/L1/follow-ups")).length;
    const before = followUpReads();
    fireEvent.click(within(form).getByRole("button", { name: "Save call" }));
    expect(await screen.findByText("Call logged.")).toBeTruthy();
    await waitFor(() => expect(screen.getByText("Lost", { selector: "strong" })).toBeTruthy());
    await waitFor(() => expect(followUpReads()).toBeGreaterThan(before));
  });

  it("shows the messages with Send WhatsApp only for the lead's telecaller, and the header WhatsApp opens the composer (tel-013)", async () => {
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen={false} />);
    expect(await screen.findByText("No messages sent yet.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "WhatsApp Asha Rao" }));
    expect(await screen.findByLabelText("Message")).toBeTruthy();
    cleanup();
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen />); // a manager reads only (WA2)
    expect(await screen.findByText("No messages sent yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Send WhatsApp" })).toBeNull();
    expect(screen.queryByRole("button", { name: "WhatsApp Asha Rao" })).toBeNull();
    cleanup();
    render(<LeadDetailPanel initial={detail({ whatsapp_to: null })} timeline={pageOf([])} canReopen={false} />); // AC3
    expect(await screen.findByText("No WhatsApp or mobile number on this lead.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "WhatsApp Asha Rao" })).toBeNull();
  });

  it("shows the counselling appointments, with Book only for the lead's telecaller on an open lead (tel-016)", async () => {
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen={false} />);
    expect(await screen.findByText("No counselling appointments yet.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Book counselling" })).toBeTruthy();
    cleanup();
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen />); // a manager reads only (AP2)
    expect(await screen.findByText("No counselling appointments yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Book counselling" })).toBeNull();
    cleanup();
    render(<LeadDetailPanel initial={detail({ status: "lost", status_label: "Lost" })} timeline={pageOf([])} canReopen={false} />); // AP11
    expect(await screen.findByText("No counselling appointments yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Book counselling" })).toBeNull();
  });

  it("shows the §2 lead fields, the enquiry and a Call link", () => {
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen={false} />);
    for (const text of ["LD-000042", "Hyderabad", "Telangana", "B.Tech", "2024", "JNTU", "Instagram", "Sep 2026", "Cyber Security", "Tara Caller", "Please call after 6pm"]) {
      expect(screen.getAllByText(text, { exact: false }).length).toBeGreaterThan(0);
    }
    expect(screen.getByRole("link", { name: "Call Asha Rao" }).getAttribute("href")).toBe("tel:+919876543210");
    expect(screen.getByText("Not assigned")).toBeTruthy(); // counselor
    expect(screen.getByText("No activity yet.")).toBeTruthy();
  });

  it("saves a new priority and shows it in the activity list (AC3)", async () => {
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen={false} />);
    const group = screen.getByRole("group", { name: "Priority" });
    expect(within(group).getByText("Ready to join / immediate requirement.")).toBeTruthy();
    fireEvent.click(within(group).getByLabelText(/Hot/));
    timeline = [priorityRow];
    fireEvent.click(screen.getByRole("button", { name: "Save priority" }));
    expect((await screen.findByText("Priority updated.")).getAttribute("role")).toBe("status");
    expect(JSON.parse(String(calls("PATCH")[0][1].body))).toEqual({ priority: "hot" });
    expect(String(calls("PATCH")[0][0])).toBe("/api/v1/telecaller/leads/L1");
    const activity = await screen.findByRole("list", { name: "Lead activity" });
    expect(within(activity).getByText("Priority: Warm → Hot")).toBeTruthy();
  });

  it("does not send an unchanged priority", () => {
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen={false} />);
    expect((screen.getByRole("button", { name: "Save priority" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("edits the contact details and shows the server's 422 message", async () => {
    patchReply = () => res({ detail: [{ msg: "Value error, Enter a valid email address" }] }, 422);
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit details" }));
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "bad" } });
    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Enter a valid email address");

    patchReply = (body) => res({ ...detail(), ...body, product: { id: "p2", name: "Java" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: " meena@example.com " } });
    fireEvent.change(screen.getByLabelText("City"), { target: { value: "" } });
    await waitFor(() => expect(screen.getByRole("option", { name: "Java" })).toBeTruthy());
    fireEvent.change(screen.getByLabelText("Product interest"), { target: { value: "p2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    expect(await screen.findByText("Details saved.")).toBeTruthy();
    expect(JSON.parse(String(calls("PATCH")[1][1].body))).toEqual({ email: "meena@example.com", city: null, product_id: "p2" });
    expect(screen.queryByRole("button", { name: "Save details" })).toBeNull();
    expect(screen.getAllByText("Java").length).toBeGreaterThan(0);
  });

  it("moves the stage through the telecaller route", async () => {
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Change stage for Asha Rao" }));
    fireEvent.change(screen.getByLabelText("New stage for Asha Rao"), { target: { value: "qualified" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Stage updated.")).toBeTruthy();
    expect(String(calls("POST")[0][0])).toBe("/api/v1/telecaller/leads/L1/stage");
    expect(JSON.parse(String(calls("POST")[0][1].body))).toEqual({ to_stage: "qualified" });
    expect(screen.getAllByText("Qualified").length).toBeGreaterThan(0);
  });

  it("is read-only once the lead is with the counselor (AC4)", () => {
    render(<LeadDetailPanel initial={detail({ read_only: true, counselor: { id: "c9", full_name: "Kiran Counselor" } })} timeline={pageOf([priorityRow])} canReopen={false} />);
    expect(screen.getByText(/with the counselor/)).toBeTruthy();
    expect(screen.getByText("Kiran Counselor")).toBeTruthy();
    for (const name of ["Save priority", "Edit details", "Change stage for Asha Rao"]) expect(screen.queryByRole("button", { name })).toBeNull();
    expect(screen.queryByRole("group", { name: "Priority" })).toBeNull();
    expect(screen.getByRole("link", { name: "Call Asha Rao" })).toBeTruthy(); // reading includes calling the number
    expect(within(screen.getByRole("list", { name: "Lead activity" })).getByText("Priority: Warm → Hot")).toBeTruthy();
  });

  it("tells a manager the lead is with the counselor but keeps the controls (QA-05)", () => {
    render(<LeadDetailPanel initial={detail({ counselor: { id: "c9", full_name: "Kiran Counselor" } })} timeline={pageOf([])} canReopen />);
    expect(screen.getByText(/This lead is with the counselor, Kiran Counselor\.$/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save priority" })).toBeTruthy();
  });

  it("shows the active call script of the lead's product (tel-012 C2)", async () => {
    scripts = () => res(pageOf([script]));
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen={false} />);
    const steps = await screen.findByRole("list", { name: "Call script steps" });
    expect(within(steps).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["GreetIntroduce yourself", "Ask about background"]);
    const url = String(fetchMock.mock.calls.map(([u]) => String(u)).find((u) => u.startsWith("/api/v1/telecaller/scripts")));
    expect(Object.fromEntries(new URLSearchParams(url.split("?")[1]))).toEqual({ product_id: "p1", active: "true", limit: "1" });
  });

  it("says when the product has no script, when the lead has no product, and when the script fails to load", async () => {
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen={false} />);
    expect(await screen.findByText("No active call script for Cyber Security yet.")).toBeTruthy();
    cleanup();
    render(<LeadDetailPanel initial={detail({ product: null })} timeline={pageOf([])} canReopen={false} />);
    expect(screen.getByText("Set the lead's product interest to see its call script.")).toBeTruthy();
    expect(fetchMock.mock.calls.filter(([u]) => String(u).startsWith("/api/v1/telecaller/scripts"))).toHaveLength(1);
    cleanup();
    scripts = () => res({ detail: "boom" }, 500);
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen={false} />);
    expect(await screen.findByText("Unable to load the call script.")).toBeTruthy();
  });

  it("loads the new product's script after the product is changed", async () => {
    scripts = () => res(pageOf([script]));
    patchReply = (body) => res({ ...detail(), ...body, product: { id: "p2", name: "Java" } });
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen={false} />);
    await screen.findByRole("list", { name: "Call script steps" });
    scripts = () => res(pageOf([]));
    fireEvent.click(screen.getByRole("button", { name: "Edit details" }));
    await waitFor(() => expect(screen.getByRole("option", { name: "Java" })).toBeTruthy());
    fireEvent.change(screen.getByLabelText("Product interest"), { target: { value: "p2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    expect(await screen.findByText("No active call script for Java yet.")).toBeTruthy();
  });

  it("says when the activity list could not be loaded", () => {
    render(<LeadDetailPanel initial={detail({ phone: null })} timeline={null} canReopen={false} />);
    expect(screen.getByText("Unable to load the activity.")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Call Asha Rao" })).toBeNull();
  });

  it("lists a further enquiry in the activity (tel-005), from a person or the website", () => {
    const enquiry: TimelineRow = { id: "e1", kind: "enquiry", at: "2026-10-06T07:00:00Z", actor: null, from_value: "website", from_label: "website",
      to_value: "Weekend batch", to_label: "Weekend batch", reason: "Please call after 6" };
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([enquiry])} canReopen={false} />);
    const activity = screen.getByRole("list", { name: "Lead activity" });
    expect(within(activity).getByText("New enquiry: Weekend batch")).toBeTruthy();
    expect(within(activity).getByText(/Website form · Website/)).toBeTruthy();
    expect(within(activity).getByText("Please call after 6")).toBeTruthy();
  });

  it("doesn't require an email when the lead has none (tel-005 I1)", () => {
    render(<LeadDetailPanel initial={detail({ email: null })} timeline={pageOf([])} canReopen={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit details" }));
    expect(screen.getByLabelText("Email").getAttribute("aria-required")).toBeNull();
  });

  it("shows the qualification section and a save updates the shared Lead details (tel-009 QD1)", async () => {
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen={false} />);
    const section = screen.getByRole("region", { name: "Qualification" });
    fireEvent.click(await within(section).findByRole("button", { name: "Edit qualification" }));
    expect(within(section).getByRole("group", { name: "IT training requirement" })).toBeTruthy();
    fireEvent.change(within(section).getByLabelText("City"), { target: { value: "Pune" } });
    fireEvent.click(within(section).getByRole("button", { name: "Save qualification" }));
    expect(await within(section).findByText("Qualification saved.")).toBeTruthy();
    expect(within(screen.getByRole("region", { name: "Lead details" })).getByText("Pune")).toBeTruthy();
  });

  it("a handed-over lead's qualification has no edit button (tel-009 AC6)", async () => {
    render(<LeadDetailPanel initial={detail({ read_only: true })} timeline={pageOf([])} canReopen={false} />);
    expect(await screen.findByText("IT training requirement")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Edit qualification" })).toBeNull();
  });
  it("offers Assign to counselor on a workable lead, not on a closed, linked or handed-over one (tel-018 HO4)", () => {
    const { unmount } = render(<LeadDetailPanel initial={detail()} timeline={pageOf([])} canReopen={false} />);
    expect(screen.getByRole("button", { name: "Assign to counselor" })).toBeTruthy();
    unmount();
    for (const over of [{ status: "lost" }, { status: "application_enrollment" }, { read_only: true, counselor: { id: "c1", full_name: "Cara" } }]) {
      const view = render(<LeadDetailPanel initial={detail(over)} timeline={pageOf([])} canReopen={false} />);
      expect(screen.queryByRole("button", { name: /counselor$/ })).toBeNull();
      view.unmount();
    }
  });

  it("a manager can change the counselor of a handed-over lead (tel-018 HO4)", () => {
    render(<LeadDetailPanel initial={detail({ counselor: { id: "c1", full_name: "Cara" } })} timeline={pageOf([])} canReopen />);
    expect(screen.getByRole("button", { name: "Change counselor" })).toBeTruthy();
  });

  it("shows the linked student's milestones (tel-018 T4)", () => {
    render(<LeadDetailPanel initial={detail({ read_only: true, status: "converted", status_label: "Converted",
      milestones: { student: { id: "s1", full_name: "Asha Rao", email: "asha@example.com" }, items: [] } })} timeline={pageOf([])} canReopen={false} />);
    expect(screen.getByRole("region", { name: "Student and milestones" })).toHaveTextContent("Linked student: Asha Rao (asha@example.com)");
  });
  it("names a counselor's return in the activity instead of Follow-up -> Follow-up (tel-018 QA-03)", () => {
    const returned: TimelineRow = { ...priorityRow, id: "h9", kind: "stage", from_value: "follow_up", from_label: "Follow-up", to_value: "follow_up",
      to_label: "Follow-up", reason: "Fees first", event: "returned", actor: { id: "c1", full_name: "Cara Counselor" } };
    render(<LeadDetailPanel initial={detail()} timeline={pageOf([returned])} canReopen={false} />);
    const activity = screen.getByRole("list", { name: "Lead activity" });
    expect(within(activity).getByText("Returned to the telecaller")).toBeTruthy();
    expect(within(activity).queryByText(/Follow-up → Follow-up/)).toBeNull();
  });
});
