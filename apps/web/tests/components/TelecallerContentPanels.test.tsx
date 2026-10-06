import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TelecallerBrochuresPanel from "@/components/TelecallerBrochuresPanel";
import TelecallerScriptsPanel from "@/components/TelecallerScriptsPanel";
import TelecallerTemplatesPanel from "@/components/TelecallerTemplatesPanel";

// tel-012: the three manager library screens. fetch is stubbed per test; the list place lives in the URL (tel-002 QA-04).
const nav = vi.hoisted(() => ({ params: new URLSearchParams(), push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: nav.push }), usePathname: () => "/telecaller/manager/x", useSearchParams: () => nav.params }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const page = (items: unknown[]) => ({ items, total: items.length, limit: 100, offset: 0 });
const cyber = { id: "p1", group: "it", name: "Cyber Security", team: "it", program: null, active: true, sort_order: 3 };
const ref = { id: "p1", name: "Cyber Security", group: "it", active: true };
const script = { id: "s1", product: ref, name: "Standard", steps: [{ title: "Introduction", notes: "Greet" }, { title: "Explain course", notes: null }], active: true };
const brochure = { id: "a1", name: "Cyber brochure", kind: "brochure", product: ref, file_name: "cyber.pdf", size_bytes: 2048, active: true, uploaded_at: "2026-10-06T05:00:00Z" };
const template = {
  id: "t1", channel: "whatsapp", kind: "course_details", name: "Course details", product: null, asset: { id: "a1", name: "Cyber brochure", active: true },
  subject: null, body: "Hi {name}: {brochure_link}", active: true,
};

type Call = { url: string; init?: RequestInit };
function serve(handler: (call: Call) => Response | undefined) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const call = { url: String(url), init };
    calls.push(call);
    const own = handler(call);
    if (own) return Promise.resolve(own);
    if (call.url.includes("/telecaller/products")) return Promise.resolve(res(page([cyber])));
    if (call.url.includes("/telecaller/assets?")) return Promise.resolve(res(page([brochure])));
    return Promise.resolve(res(page([])));
  }));
  return calls;
}
const posted = (calls: Call[], method = "POST") => calls.filter((c) => c.init?.method === method);

afterEach(() => {
  cleanup();
  nav.params = new URLSearchParams();
  nav.push.mockReset();
  vi.unstubAllGlobals();
});

describe("TelecallerScriptsPanel (tel-012)", () => {
  it("lists a script with its product and ordered steps", async () => {
    serve(({ url }) => (url.includes("/scripts") ? res(page([script])) : undefined));
    render(<TelecallerScriptsPanel />);
    const row = (await screen.findByText("Standard")).closest("tr")!;
    expect(within(row).getByText("Cyber Security")).toBeInTheDocument();
    expect(within(row).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Introduction — Greet", "Explain course"]);
  });

  it("shows the empty state, and the load error with Retry", async () => {
    serve(() => undefined);
    render(<TelecallerScriptsPanel />);
    expect(await screen.findByText("No scripts yet.")).toBeInTheDocument();
    cleanup();
    serve(({ url }) => (url.includes("/scripts") ? res({ detail: "x" }, 500) : undefined));
    render(<TelecallerScriptsPanel />);
    expect(await screen.findByText("Unable to load scripts.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("creates a script with ordered steps, posting once on a double click", async () => {
    const calls = serve(({ init }) => (init?.method === "POST" ? res(script, 201) : undefined));
    render(<TelecallerScriptsPanel />);
    await screen.findAllByRole("option", { name: "Cyber Security" }); // the form's picker and the list filter
    fireEvent.change(screen.getByLabelText("Product (required)"), { target: { value: "p1" } });
    fireEvent.change(screen.getByLabelText("Script name (required)"), { target: { value: " Standard " } });
    fireEvent.change(screen.getByLabelText("Step 1 title"), { target: { value: "Explain course" } });
    fireEvent.click(screen.getByRole("button", { name: "Add step" }));
    fireEvent.change(screen.getByLabelText("Step 2 title"), { target: { value: "Introduction" } });
    fireEvent.change(screen.getByLabelText("Step 2 talking points"), { target: { value: " Greet " } });
    fireEvent.click(screen.getByRole("button", { name: "Move step 2 up" }));
    const button = screen.getByRole("button", { name: "Create script" });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(await screen.findByText("Created Standard.")).toBeInTheDocument();
    expect(posted(calls)).toHaveLength(1);
    expect(JSON.parse(String(posted(calls)[0].init!.body))).toEqual({
      product_id: "p1", name: "Standard", steps: [{ title: "Introduction", notes: "Greet" }, { title: "Explain course", notes: null }],
    });
  });

  it("keeps at least one step and at most 20", async () => {
    serve(() => undefined);
    render(<TelecallerScriptsPanel />);
    expect(screen.getByRole("button", { name: "Remove step 1" })).toBeDisabled();
    for (let i = 0; i < 19; i++) fireEvent.click(screen.getByRole("button", { name: "Add step" }));
    expect(screen.getByLabelText("Step 20 title")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add step" })).toBeDisabled();
  });

  it("shows the server's sentence when a second active script is refused", async () => {
    serve(({ url, init }) =>
      init?.method === "PATCH" ? res({ detail: "Cyber Security already has an active script. Deactivate it first." }, 409)
        : url.includes("/scripts") ? res(page([{ ...script, active: false }])) : undefined);
    render(<TelecallerScriptsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Reactivate Standard" }));
    expect(await screen.findByText("Cyber Security already has an active script. Deactivate it first.")).toBeInTheDocument();
  });
});

describe("TelecallerTemplatesPanel (tel-012)", () => {
  it("asks for a subject only for email and offers that channel's kinds", async () => {
    serve(() => undefined);
    render(<TelecallerTemplatesPanel />);
    expect(screen.queryByLabelText("Subject (required)")).not.toBeInTheDocument();
    expect(within(screen.getByLabelText("Kind (required)")).getByRole("option", { name: "Welcome message" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Channel (required)"), { target: { value: "email" } });
    expect(screen.getByLabelText("Subject (required)")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Kind (required)")).getByRole("option", { name: "Fee proposal" })).toBeInTheDocument();
    expect(within(screen.getByLabelText("Kind (required)")).queryByRole("option", { name: "Welcome message" })).not.toBeInTheDocument();
  });

  it("warns about an unknown placeholder and counts characters", async () => {
    serve(() => undefined);
    render(<TelecallerTemplatesPanel />);
    fireEvent.change(screen.getByLabelText("Message (required)"), { target: { value: "Hi {first_name}" } });
    expect(screen.getByText("Unknown placeholder: {first_name}")).toBeInTheDocument();
    expect(screen.getByText("15 / 1000")).toBeInTheDocument();
  });

  it("creates a WhatsApp template linked to a brochure", async () => {
    const calls = serve(({ init }) => (init?.method === "POST" ? res(template, 201) : undefined));
    render(<TelecallerTemplatesPanel />);
    await screen.findByRole("option", { name: "Cyber brochure" });
    fireEvent.change(screen.getByLabelText("Kind (required)"), { target: { value: "course_details" } });
    fireEvent.change(screen.getByLabelText("Template name (required)"), { target: { value: "Course details" } });
    fireEvent.change(screen.getByLabelText("Brochure"), { target: { value: "a1" } });
    fireEvent.change(screen.getByLabelText("Message (required)"), { target: { value: "Hi {name}: {brochure_link}" } });
    fireEvent.click(screen.getByRole("button", { name: "Create template" }));
    expect(await screen.findByText("Created Course details.")).toBeInTheDocument();
    expect(JSON.parse(String(posted(calls)[0].init!.body))).toEqual({
      channel: "whatsapp", kind: "course_details", name: "Course details", product_id: null, asset_id: "a1", body: "Hi {name}: {brochure_link}",
    });
  });

  it("previews a template with sample values and its brochure link", async () => {
    serve(({ url }) =>
      url.includes("/preview") ? res({ subject: null, body: "Hi Priya Sharma: https://x/l", brochure_link: { url: "https://x/l", expires_at: "2026-10-13T05:00:00Z" } })
        : url.includes("/templates?") ? res(page([template])) : undefined);
    render(<TelecallerTemplatesPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Preview Course details" }));
    expect(await screen.findByText("Hi Priya Sharma: https://x/l")).toBeInTheDocument();
    expect(screen.getByText(/Sample values/)).toBeInTheDocument();
  });
});

describe("TelecallerBrochuresPanel (tel-012)", () => {
  const pdf = () => new File(["%PDF-1.4"], "cyber.pdf", { type: "application/pdf" });

  it("uploads a PDF as multipart form data", async () => {
    const calls = serve(({ init }) => (init?.method === "POST" ? res(brochure, 201) : undefined));
    render(<TelecallerBrochuresPanel />);
    await screen.findByRole("option", { name: "Cyber Security" });
    fireEvent.change(screen.getByLabelText("Brochure name (required)"), { target: { value: "Cyber brochure" } });
    fireEvent.change(screen.getByLabelText("Kind (required)"), { target: { value: "fee" } });
    fireEvent.change(screen.getByLabelText("Product"), { target: { value: "p1" } });
    fireEvent.change(screen.getByLabelText("PDF file (required)"), { target: { files: [pdf()] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload brochure" }));
    expect(await screen.findByText("Uploaded Cyber brochure.")).toBeInTheDocument();
    const body = posted(calls)[0].init!.body as FormData;
    expect([body.get("name"), body.get("kind"), body.get("product_id"), (body.get("file") as File).name]).toEqual(["Cyber brochure", "fee", "p1", "cyber.pdf"]);
  });

  it("refuses a non-PDF before uploading", async () => {
    const calls = serve(() => undefined);
    render(<TelecallerBrochuresPanel />);
    fireEvent.change(screen.getByLabelText("Brochure name (required)"), { target: { value: "Photo" } });
    fireEvent.change(screen.getByLabelText("PDF file (required)"), { target: { files: [new File(["x"], "photo.png", { type: "image/png" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload brochure" }));
    expect(await screen.findByText("Upload a PDF file")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("PDF file (required)"), { target: { files: [] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload brochure" }));
    expect(await screen.findByText("Choose a PDF file")).toBeInTheDocument();
    expect(posted(calls)).toHaveLength(0);
  });

  it("copies a 7-day link and says until when it works", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    serve(({ url, init }) =>
      url.endsWith("/link") && init?.method === "POST" ? res({ url: "http://localhost:3082/api/v1/public/telecaller-assets/tok", expires_at: "2026-10-13T05:00:00Z" })
        : url.includes("/assets?") ? res(page([brochure])) : undefined);
    render(<TelecallerBrochuresPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Copy link for Cyber brochure" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("http://localhost:3082/api/v1/public/telecaller-assets/tok"));
    expect(await screen.findByText(/Link copied for Cyber brochure\. It works until 13/)).toBeInTheDocument();
  });

  it("shows the link to copy by hand when the clipboard is unavailable", async () => {
    Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true });
    serve(({ url, init }) =>
      url.endsWith("/link") && init?.method === "POST" ? res({ url: "http://h/l", expires_at: "2026-10-13T05:00:00Z" })
        : url.includes("/assets?") ? res(page([brochure])) : undefined);
    render(<TelecallerBrochuresPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Copy link for Cyber brochure" }));
    expect(await screen.findByDisplayValue("http://h/l")).toBeInTheDocument();
  });
});
