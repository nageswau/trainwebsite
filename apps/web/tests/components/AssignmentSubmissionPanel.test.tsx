import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AssignmentSubmissionPanel from "@/components/AssignmentSubmissionPanel";

// nehn-024 (DEC-SCOPE-291 F9/F10): files are picked, dropped or photographed, uploaded through nehn-003, then submitted by id.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row = (submission_type: string) => ({ id: "a1", title: "Week 1 scan", due: "2026-11-01T10:00:00Z", submission: "not submitted", score: null, feedback: null, submission_type });
const file = (name: string, size: number, type: string) => {
  const f = new File(["x"], name, { type });
  Object.defineProperty(f, "size", { value: size });
  return f;
};

type Call = { url: string; init?: RequestInit };
function serve(submissionType: string, onUpload: (n: number) => Response = (n) => res({ id: `f${n}` }, 201)) {
  const calls: Call[] = [];
  let uploads = 0;
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    if (String(url).includes("/portal/")) return Promise.resolve(res({ rows: [row(submissionType)] }));
    if (String(url).includes("/files/upload")) return Promise.resolve(onUpload(++uploads));
    return Promise.resolve(res({ id: "s1", status: "submitted", is_late: false }, 201));
  }));
  return calls;
}

async function open() {
  render(<AssignmentSubmissionPanel section="assignments" />);
  fireEvent.click(await screen.findByRole("button", { name: "Submit this work" }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AssignmentSubmissionPanel", () => {
  it("says what the work needs", async () => {
    serve("file");
    await open();
    expect(screen.getByText("Attach at least one file.")).toBeTruthy();
  });

  it("uploads each picked file for the submission purpose, then submits their ids", async () => {
    const calls = serve("text_or_file");
    await open();
    fireEvent.change(screen.getByLabelText("Choose files"), { target: { files: [file("page-1.pdf", 3 * 1024 * 1024, "application/pdf"), file("page-2.heic", 900_000, "")] } });
    expect(screen.getByText("page-1.pdf")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(await screen.findByText("Submitted on time.")).toBeTruthy();
    const uploads = calls.filter((c) => c.url.includes("/files/upload"));
    expect(uploads.map((c) => c.url)).toEqual(["/api/v1/files/upload?purpose=assignment_submission", "/api/v1/files/upload?purpose=assignment_submission"]);
    expect(((uploads[1].init?.body as FormData).get("file") as File).type).toBe("image/heic");  // an untyped HEIC is typed by extension
    const submit = calls.find((c) => c.url.includes("/submissions"));
    expect(JSON.parse(String(submit?.init?.body))).toEqual({ answer: null, file_url: null, file_ids: ["f1", "f2"] });
  });

  it("refuses an oversize or disallowed file before uploading, and a file can be removed", async () => {
    const calls = serve("file");
    await open();
    fireEvent.change(screen.getByLabelText("Choose files"), { target: { files: [file("big.pdf", 6 * 1024 * 1024, "application/pdf"), file("notes.zip", 10, "application/zip"), file("ok.png", 10, "image/png")] } });
    expect(screen.getByRole("alert").textContent).toContain("big.pdf is larger than 5 MB.");
    expect(screen.getByRole("alert").textContent).toContain("notes.zip is not an allowed type (PDF, Word, JPG, PNG or HEIC).");
    expect(screen.queryByText("big.pdf")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Remove ok.png" }));
    expect(screen.queryByText("ok.png")).toBeNull();
    expect(calls.some((c) => c.url.includes("/files/upload"))).toBe(false);
  });

  it("adds dropped files", async () => {
    serve("file");
    await open();
    fireEvent.drop(screen.getByText(/Drag files here/), { dataTransfer: { files: [file("scan.jpg", 10, "image/jpeg")] } });
    expect(screen.getByText("scan.jpg")).toBeTruthy();
    expect(screen.getByText("1 KB")).toBeTruthy();  // QA-01: a small file is not "0.0 MB"
  });

  it("offers the camera for a photo of handwritten work", async () => {
    serve("file");
    await open();
    const camera = screen.getByLabelText("Take a photo");
    expect(camera.getAttribute("capture")).toBe("environment");
    expect(camera.getAttribute("accept")).toBe("image/*");
  });

  it("shows the server's refusal and does not submit when an upload fails", async () => {
    const calls = serve("file", () => res({ detail: "The file's contents do not match its type" }, 415));
    await open();
    fireEvent.change(screen.getByLabelText("Choose files"), { target: { files: [file("fake.pdf", 10, "application/pdf")] } });
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    await waitFor(() => expect(screen.getByText("fake.pdf: The file's contents do not match its type")).toBeTruthy());
    expect(calls.some((c) => c.url.includes("/submissions"))).toBe(false);
  });
});
