import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterMessages from "@/components/RecruiterMessages";
import RecruiterRequirementMessages from "@/components/RecruiterRequirementMessages";
import RecruiterTemplateLibrary from "@/components/RecruiterTemplateLibrary";
import type { GovernedTemplate } from "@/lib/recruiterMessages";

const push = vi.fn();
const search = vi.hoisted(() => ({ value: "" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), usePathname: () => "/recruiter/templates", useSearchParams: () => new URLSearchParams(search.value) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const page = (items: unknown[]) => ({ items, total: items.length, limit: 25, offset: 0 });
const tpl = (over: Partial<GovernedTemplate> = {}): GovernedTemplate => ({
  id: "t1", channel: "linkedin", kind: null, name: "Connect note", subject: null, body: "Hi {name}", active: true, category: "linkedin",
  purpose: "First touch", language: "English", department: null, industry: null, role_type: null, status: "approved", visibility: "shared",
  steps: null, version: 2, created_by: { id: "u1", full_name: "Asha" }, updated_by: { id: "u2", full_name: "Meera Lead" }, created_at: "2026-11-01T05:00:00Z",
  updated_at: "2026-11-02T05:00:00Z", last_used_at: null, can_edit: false, can_approve: false, can_archive: false, can_restore: false, ...over,
});

type Call = { url: string; init?: RequestInit };
function serve(routes: (url: string) => Response, onWrite: (call: Call) => Response = () => res({}, 201)) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const call = { url: String(url), init };
    calls.push(call);
    return Promise.resolve(init?.method && init.method !== "GET" ? onWrite(call) : routes(String(url)));
  }));
  return calls;
}
const posts = (calls: Call[]) => calls.filter((c) => c.init?.method === "POST");
const contacts = { items: [{ id: "k1", name: "Priya", active: true, mobile: "98765 43210", email: "p@abc.example.com", whatsapp_to: "919876543210" }], can_edit: true };

beforeEach(() => push.mockReset());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("pob-023 the requirement page's messages (QA-07)", () => {
  const company = (can_edit: boolean) => ({ company: { id: "co1", permissions: { can_edit } } });

  it("shows nothing when the company is outside the caller's scope", async () => {
    const calls = serve((url) => (url.endsWith("/companies/co1") ? res({ detail: "Company not found" }, 404) : res(page([]))));
    const { container } = render(<RecruiterRequirementMessages companyId="co1" jobId="j1" />);
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/companies/co1"))).toBe(true));
    await waitFor(() => expect(container.textContent).toBe(""));
    expect(calls.filter((c) => c.url.includes("/messages") || c.url.includes("/contacts"))).toEqual([]);
  });

  it("offers the composer on the company's write right, not the requirement's", async () => {
    serve((url) => {
      if (url.endsWith("/companies/co1")) return res(company(true));
      if (url.includes("/contacts")) return res(contacts);
      return res(page([]));
    });
    render(<RecruiterRequirementMessages companyId="co1" jobId="j1" />);
    expect(await screen.findByRole("button", { name: "LinkedIn message" })).toBeTruthy();
  });

  it("is read-only for a caller who reads the company but cannot write to it", async () => {
    serve((url) => (url.endsWith("/companies/co1") ? res(company(false)) : res(page([]))));
    render(<RecruiterRequirementMessages companyId="co1" jobId="j1" />);
    expect(await screen.findByRole("heading", { name: "Messages" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "LinkedIn message" })).toBeNull();
  });

  it("says so and retries when the company cannot be loaded", async () => {
    let up = false;
    serve((url) => {
      if (url.endsWith("/companies/co1")) return up ? res(company(false)) : res({}, 500);
      return res(page([]));
    });
    render(<RecruiterRequirementMessages companyId="co1" jobId="j1" />);
    expect(await screen.findByText("Unable to load the messages.")).toBeTruthy();
    up = true;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Messages" })).toBeTruthy();
  });
});

describe("pob-023 copy mode (G10/G11)", () => {
  it("copies a LinkedIn message only after the preview, with the requirement as context, and logs the copy (AC4)", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const calls = serve((url) => {
      if (url.includes("/contacts")) return res(contacts);
      if (url.includes("/templates")) return res(page([tpl()]));
      if (url.includes("/render")) return res({ template: tpl(), subject: null, body: "Hi Priya, Java Developer in Pune", steps: null, missing: [] });
      return res(page([]));
    });
    render(<RecruiterMessages source={{ kind: "requirement", companyId: "co1", jobId: "j1" }} canWrite />);
    fireEvent.click(await screen.findByRole("button", { name: "LinkedIn message" }));
    expect(screen.queryByRole("button", { name: "Copy to clipboard" })).toBeNull(); // no copy before a preview
    const picker = await screen.findByLabelText("Template");
    await waitFor(() => expect(within(picker).getAllByRole("option")).toHaveLength(2));
    expect(calls.some((c) => c.url.includes("channel=linkedin&usable=true"))).toBe(true);
    fireEvent.change(picker, { target: { value: "t1" } });
    await waitFor(() => expect((screen.getByLabelText(/Message \(preview/) as HTMLTextAreaElement).value).toBe("Hi Priya, Java Developer in Pune"));
    expect(calls.some((c) => c.url.includes("render?template_id=t1&contact_id=k1&job_id=j1"))).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Copy to clipboard" }));
    await screen.findByText("LinkedIn message for Priya copied and logged.");
    expect(writeText).toHaveBeenCalledWith("Hi Priya, Java Developer in Pune");
    expect(JSON.parse(String(posts(calls)[0].init?.body))).toEqual({ contact_id: "k1", channel: "linkedin", template_id: "t1" });
  });

  it("shows a calling script's numbered steps and copies them with the opening (AC5)", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const script = tpl({ id: "c1", channel: "call", category: "calling", name: "Intro call", steps: ["Introduce yourself", "Ask about roles"] });
    serve((url) => {
      if (url.includes("/contacts")) return res(contacts);
      if (url.includes("/templates")) return res(page([script]));
      if (url.includes("/render")) return res({ template: script, subject: null, body: "Opening", steps: ["Introduce yourself", "Ask about roles"], missing: [] });
      return res(page([]));
    });
    render(<RecruiterMessages source={{ kind: "company", companyId: "co1" }} canWrite />);
    fireEvent.click(await screen.findByRole("button", { name: "Calling script" }));
    fireEvent.change(await screen.findByLabelText("Template"), { target: { value: "c1" } });
    const steps = await screen.findByRole("list", { name: "Steps" });
    expect(within(steps).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Introduce yourself", "Ask about roles"]);
    fireEvent.click(screen.getByRole("button", { name: "Copy to clipboard" }));
    await screen.findByText("Calling script for Priya copied and logged.");
    expect(writeText).toHaveBeenCalledWith("Opening\n\n1. Introduce yourself\n2. Ask about roles");
  });

  it("does not log a copy the browser refused", async () => {
    vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn().mockRejectedValue(new Error("denied")) } });
    const calls = serve((url) => {
      if (url.includes("/contacts")) return res(contacts);
      if (url.includes("/templates")) return res(page([tpl()]));
      if (url.includes("/render")) return res({ template: tpl(), subject: null, body: "Hi", steps: null, missing: [] });
      return res(page([]));
    });
    render(<RecruiterMessages source={{ kind: "company", companyId: "co1" }} canWrite />);
    fireEvent.click(await screen.findByRole("button", { name: "LinkedIn message" }));
    const picker = await screen.findByLabelText("Template");
    await waitFor(() => expect(within(picker).getAllByRole("option")).toHaveLength(2));
    fireEvent.change(picker, { target: { value: "t1" } });
    fireEvent.click(await screen.findByRole("button", { name: "Copy to clipboard" }));
    await screen.findByText(/blocked the clipboard/);
    expect(posts(calls)).toHaveLength(0);
  });
});

describe("pob-023 RecruiterTemplateLibrary", () => {
  it("adds a shared draft for a recruiter and says it waits for approval (AC1)", async () => {
    const calls = serve(() => res(page([])), () => res(tpl({ status: "draft" }), 201));
    render(<RecruiterTemplateLibrary approver={false} />);
    expect(await screen.findByText("No templates yet. Add the first one above.")).toBeTruthy();
    const createForm = screen.getByRole("form", { name: "Add a template" });
    expect(createForm.querySelector(".form-message, .form-error")).toBeNull(); // QA-01: no empty coloured bar before any feedback
    fireEvent.change(screen.getByLabelText("Channel (required)"), { target: { value: "linkedin" } });
    expect(screen.queryByLabelText("Kind (required)")).toBeNull(); // LinkedIn has no kind
    fireEvent.change(screen.getByLabelText("Template name (required)"), { target: { value: "Connect note" } });
    fireEvent.change(screen.getByLabelText("Message (required)"), { target: { value: "Hi {name} {salary}" } });
    expect(screen.getByText("Unknown placeholder: {salary}")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Message (required)"), { target: { value: "Hi {name}" } });
    fireEvent.click(screen.getByRole("button", { name: "Add template" }));
    await screen.findByText(/as a draft\. The Team Lead approves it/);
    const body = JSON.parse(String(posts(calls)[0].init?.body));
    expect(body).toMatchObject({ channel: "linkedin", category: "linkedin", name: "Connect note", body: "Hi {name}", visibility: "shared", language: "English" });
    expect(body.kind).toBeUndefined();
  });

  it("keeps what was typed when the channel changes (QA-02)", async () => {
    serve(() => res(page([])));
    render(<RecruiterTemplateLibrary approver={false} />);
    await screen.findByText("No templates yet. Add the first one above.");
    fireEvent.change(screen.getByLabelText("Template name (required)"), { target: { value: "Connect note" } });
    fireEvent.change(screen.getByLabelText("Purpose"), { target: { value: "First touch" } });
    fireEvent.change(screen.getByLabelText("Message (required)"), { target: { value: "Hi {name}" } });
    fireEvent.change(screen.getByLabelText("Channel (required)"), { target: { value: "linkedin" } });
    expect((screen.getByLabelText("Template name (required)") as HTMLInputElement).value).toBe("Connect note");
    expect((screen.getByLabelText("Purpose") as HTMLInputElement).value).toBe("First touch");
    expect((screen.getByLabelText("Message (required)") as HTMLTextAreaElement).value).toBe("Hi {name}");
    expect((screen.getByLabelText("Category (required)") as HTMLSelectElement).value).toBe("linkedin"); // still follows the channel
  });

  it("uses the shared stacking table, so a row's actions stay on a phone screen (QA-01)", async () => {
    serve(() => res(page([tpl()])));
    render(<RecruiterTemplateLibrary approver={false} />);
    expect((await screen.findByRole("table")).className).toBe("table stack compact");
  });

  it("offers the way back from a page past the end, and doesn't claim the library is empty (QA-03)", async () => {
    search.value = "offset=99999";
    serve(() => res({ items: [], total: 16, limit: 25, offset: 99999 }));
    render(<RecruiterTemplateLibrary approver={false} />);
    fireEvent.click(await screen.findByRole("button", { name: "Back to the first page" }));
    expect(push).toHaveBeenCalledWith("/recruiter/templates", { scroll: false });
    expect(screen.queryByText("No templates yet. Add the first one above.")).toBeNull();
    search.value = "";
  });

  it("lets the Team Lead approve a draft and read its versions (AC1, AC2)", async () => {
    const draft = tpl({ id: "d1", channel: "whatsapp", kind: "follow_up", category: "whatsapp", name: "Chase JD", status: "draft", can_approve: true, can_edit: true, can_archive: true });
    const calls = serve((url) => {
      if (url.includes("/versions")) return res({ items: [{ version: 2, created_at: "2026-11-02T05:00:00Z", edited_by: { id: "u2", full_name: "Meera Lead" }, name: "Chase JD", subject: null, body: "Hello {name}" }], total: 1 });
      return res(page([draft]));
    }, () => res(tpl({ ...draft, status: "approved" })));
    render(<RecruiterTemplateLibrary approver />);
    const row = (await screen.findByText("Chase JD", { selector: "strong" })).closest("tr") as HTMLElement;
    expect(within(row).getByText("Draft")).toBeTruthy();
    fireEvent.click(within(row).getByRole("button", { name: /^Versions/ }));
    expect(await screen.findByText(/Hello \{name\}/)).toBeTruthy();
    fireEvent.click(within(row).getByRole("button", { name: /^Approve/ }));
    await screen.findByText("Approved Chase JD. The team can use it now.");
    expect(posts(calls)[0].url).toBe("/api/v1/recruiter/templates/d1/approve");
  });

  it("shows the API's error and a retry when the list fails", async () => {
    serve(() => res({ detail: "boom" }, 500));
    render(<RecruiterTemplateLibrary approver />);
    expect(await screen.findByText("Unable to load the templates.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });
});
