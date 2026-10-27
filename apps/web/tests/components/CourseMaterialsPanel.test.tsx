import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CourseMaterialsPanel from "@/components/CourseMaterialsPanel";

// nehn-027 (DEC-SCOPE-294 M10): the trainer publishes a file or a link, then edits, reorders and deletes the batch's materials.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const API = "/api/v1/workflows/it/trainer/materials";
const batches = [{ id: "b1", name: "FastAPI Jan", schedule: "Mon 7pm" }, { id: "b2", name: "React Feb", schedule: "Tue 7pm" }];
const notes = { id: "m1", batch_id: "b1", batch: "FastAPI Jan", title: "Week 1 notes", resource_type: "document", url: `/api/v1/workflows/it/materials/m1/file`, sort_order: 0, file: { filename: "week-1.pdf", content_type: "application/pdf", size: 3 * 1024 * 1024 } };
const video = { id: "m2", batch_id: "b1", batch: "FastAPI Jan", title: "Class recording", resource_type: "video", url: "https://youtu.be/abc", sort_order: 1, file: null };

type Call = { url: string; method: string; body: unknown };

function serve(list: unknown[] | "fail" = [notes, video]) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method || "GET";
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : init?.body;
    calls.push({ url: String(url), method, body });
    const json = (data: unknown, status = 200) => Promise.resolve(new Response(status === 204 ? null : JSON.stringify(data), { status }));
    if (method === "GET" && String(url).startsWith(API)) return list === "fail" ? json({ detail: "Materials are unavailable" }, 500) : json(list);
    if (String(url).startsWith("/api/v1/files/upload")) return json({ id: "f-1" }, 201);
    if (method === "POST") return json({ id: "m9" }, 201);
    if (method === "DELETE") return json(null, 204);
    return json({});
  }));
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const pdf = (size = 1024) => new File([new Uint8Array(size)], "week-2.pdf", { type: "application/pdf" });

describe("CourseMaterialsPanel", () => {
  it("uploads a file then publishes it with the file id", async () => {
    const calls = serve();
    render(<CourseMaterialsPanel batches={batches} />);
    const form = screen.getByRole("form", { name: "Publish course material" });
    fireEvent.click(within(form).getByLabelText("Upload a file"));
    fireEvent.change(within(form).getByLabelText("Batch"), { target: { value: "b1" } });
    fireEvent.change(within(form).getByLabelText("Title"), { target: { value: "Week 2 notes" } });
    expect(within(form).queryByRole("option", { name: "Video" })).toBeNull(); // M3: videos stay links
    fireEvent.change(within(form).getByLabelText(/^File/), { target: { files: [pdf()] } });
    fireEvent.submit(form);
    expect(await screen.findByText("Material published.")).toBeTruthy();
    expect(calls.find(c => c.url.startsWith("/api/v1/files/upload"))?.url).toBe("/api/v1/files/upload?purpose=learning_material");
    const created = calls.find(c => c.url === API && c.method === "POST");
    expect(created?.body).toEqual({ batch_id: "b1", title: "Week 2 notes", resource_type: "document", file_id: "f-1" });
  });

  it("refuses an oversize or video file in the browser with link guidance", async () => {
    const calls = serve();
    render(<CourseMaterialsPanel batches={batches} />);
    const form = screen.getByRole("form", { name: "Publish course material" });
    fireEvent.click(within(form).getByLabelText("Upload a file"));
    fireEvent.change(within(form).getByLabelText("Batch"), { target: { value: "b1" } });
    fireEvent.change(within(form).getByLabelText("Title"), { target: { value: "Big" } });
    fireEvent.change(within(form).getByLabelText(/^File/), { target: { files: [pdf(21 * 1024 * 1024)] } });
    fireEvent.submit(form);
    expect((await screen.findByRole("alert")).textContent).toMatch(/larger than 20 MB.*YouTube or Google Drive/);
    fireEvent.change(within(form).getByLabelText(/^File/), { target: { files: [new File(["x"], "class.mp4", { type: "video/mp4" })] } });
    fireEvent.submit(form);
    expect((await screen.findByRole("alert")).textContent).toMatch(/class\.mp4 is not a PDF.*link/);
    expect(calls.some(c => c.url.startsWith("/api/v1/files/upload"))).toBe(false);
  });

  it("publishes a link as before", async () => {
    const calls = serve();
    render(<CourseMaterialsPanel batches={batches} />);
    const form = screen.getByRole("form", { name: "Publish course material" });
    fireEvent.change(within(form).getByLabelText("Batch"), { target: { value: "b2" } });
    fireEvent.change(within(form).getByLabelText("Title"), { target: { value: "Docs" } });
    fireEvent.change(within(form).getByLabelText("Material type"), { target: { value: "video" } });
    fireEvent.change(within(form).getByLabelText("Resource URL"), { target: { value: "https://youtu.be/x" } });
    fireEvent.submit(form);
    expect(await screen.findByText("Material published.")).toBeTruthy();
    expect(calls.find(c => c.url === API && c.method === "POST")?.body).toEqual({ batch_id: "b2", title: "Docs", resource_type: "video", url: "https://youtu.be/x" });
  });

  it("lists the batch's materials and edits, reorders and deletes them", async () => {
    const calls = serve();
    render(<CourseMaterialsPanel batches={batches} />);
    const list = await screen.findByRole("list", { name: "Materials for FastAPI Jan" });
    const items = within(list).getAllByRole("listitem");
    expect(items.map(item => within(item).getByRole("heading").textContent)).toEqual(["Week 1 notes", "Class recording"]);
    expect(within(items[0]).getByText("week-1.pdf · 3.0 MB")).toBeTruthy();
    expect(within(items[0]).getByRole("button", { name: "Move Week 1 notes up" }).hasAttribute("disabled")).toBe(true);

    fireEvent.click(within(items[0]).getByRole("button", { name: "Move Week 1 notes down" }));
    await waitFor(() => expect(calls.filter(c => c.method === "PATCH")).toHaveLength(2));
    expect(calls.filter(c => c.method === "PATCH").map(c => [c.url, c.body])).toEqual([
      [`${API}/m2`, { sort_order: 0 }],
      [`${API}/m1`, { sort_order: 1 }],
    ]);

    fireEvent.click(within(items[0]).getByRole("button", { name: "Edit Week 1 notes" }));
    const edit = screen.getByRole("form", { name: "Edit Week 1 notes" });
    expect(within(edit).queryByLabelText("Resource URL")).toBeNull(); // a file has no link to edit
    fireEvent.change(within(edit).getByLabelText("Title"), { target: { value: "Week 1 slides" } });
    fireEvent.submit(edit);
    await waitFor(() => expect(calls.some(c => c.method === "PATCH" && (c.body as { title?: string }).title === "Week 1 slides")).toBe(true));
    expect(await screen.findByText("Material updated.")).toBeTruthy();

    fireEvent.click(within(items[1]).getByRole("button", { name: "Delete Class recording" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    expect(await screen.findByText("Material deleted. Students no longer see it.")).toBeTruthy();
    expect(calls.some(c => c.method === "DELETE" && c.url === `${API}/m2`)).toBe(true);
  });

  it("keeps a legacy type the picker does not list (QA-02)", async () => {
    const legacy = { ...video, id: "m3", title: "Old notes", resource_type: "pdf", url: "https://example.com/a.pdf" };
    const calls = serve([legacy]);
    render(<CourseMaterialsPanel batches={batches} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Old notes" }));
    const edit = screen.getByRole("form", { name: "Edit Old notes" });
    expect((within(edit).getByLabelText("Material type") as HTMLSelectElement).value).toBe("pdf");
    fireEvent.change(within(edit).getByLabelText("Title"), { target: { value: "Older notes" } });
    fireEvent.submit(edit);
    await waitFor(() => expect(calls.find(c => c.method === "PATCH")?.body).toEqual({ title: "Older notes" }));
  });

  it("shows empty and error states", async () => {
    serve([]);
    render(<CourseMaterialsPanel batches={batches} />);
    expect(await screen.findByText("No materials published for this batch yet.")).toBeTruthy();
    cleanup();
    serve("fail");
    render(<CourseMaterialsPanel batches={batches} />);
    expect((await screen.findByRole("alert")).textContent).toBe("Materials are unavailable");
  });
});
