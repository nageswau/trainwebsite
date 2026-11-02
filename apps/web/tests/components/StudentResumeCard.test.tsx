import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ResumeLimitPanel from "@/components/ResumeLimitPanel";
import StudentResumeCard from "@/components/StudentResumeCard";
import type { StudentResumeList, StudentResumeVersion } from "@/lib/studentResumes";

const URL = "/api/v1/counselor/it/students/s1/resumes";
const MB = 1024 * 1024;
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const version = (extra: Partial<StudentResumeVersion> = {}): StudentResumeVersion => ({
  version: 1, file_name: "Asha CV.pdf", content_type: "application/pdf", size_bytes: 20_480, visibility: "hr",
  uploaded_by: { id: "u1", full_name: "Asha Rao" }, uploaded_by_role: "it_student", created_at: "2026-11-02T10:00:00Z", ...extra,
});
const list = (items: StudentResumeVersion[], extra: Partial<StudentResumeList> = {}): StudentResumeList => ({ items, max_bytes: 5 * MB, can_upload: true, ...extra });
const file = (bytes: number, name = "cv.pdf") => new File([new Uint8Array(bytes)], name, { type: "application/pdf" });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("StudentResumeCard (itc-026)", () => {
  it("lists versions newest first with the current badge, sharing, uploader and download links", async () => {
    const two = [version({ version: 2, file_name: "v2.docx", visibility: "private", uploaded_by: { id: "c1", full_name: "Nora" }, uploaded_by_role: "counselor" }), version()];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(list(two))));
    render(<StudentResumeCard url={URL} />);
    const latest = await screen.findByRole("link", { name: "Version 2 — v2.docx" });
    expect(latest).toHaveAttribute("href", `${URL}/2/file`);
    expect(screen.getByRole("link", { name: "Version 1 — Asha CV.pdf" })).toHaveAttribute("href", `${URL}/1/file`);
    expect(screen.getAllByText("Current")).toHaveLength(1);
    expect(screen.getByText("Not shared with HR")).toBeInTheDocument();
    expect(screen.getByText(/Nora \(counselor\)/)).toBeInTheDocument();
    expect(screen.getByLabelText("Upload a new version")).toBeInTheDocument();
    expect(screen.getByText(/up to 5 MB/)).toBeInTheDocument();
  });

  it("shows the empty state, and no form or links when the reader cannot upload or download", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(list([], { can_upload: false }))));
    render(<StudentResumeCard url={URL} canDownload={false} />);
    expect(await screen.findByText("No resume uploaded yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload" })).not.toBeInTheDocument();
  });

  it("in HR's view marks the newest shared version 'Latest shared' and drops the per-row sharing badge (QA-01)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(list([version({ version: 3 }), version()], { can_upload: false }))));
    render(<StudentResumeCard url={URL} hrView />);
    await screen.findByRole("link", { name: "Version 3 — Asha CV.pdf" });
    expect(screen.getByText("Latest shared")).toBeInTheDocument();
    expect(screen.queryByText("Current")).not.toBeInTheDocument();
    expect(screen.queryByText("Shared with HR")).not.toBeInTheDocument();
  });

  it("refuses an over-limit file before sending and names the limit", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res(list([], { max_bytes: 1 * MB })));
    vi.stubGlobal("fetch", fetchMock);
    render(<StudentResumeCard url={URL} />);
    fireEvent.change(await screen.findByLabelText("Upload resume"), { target: { files: [file(2 * MB)] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The resume must be at most 1 MB.");
    expect(fetchMock).toHaveBeenCalledTimes(1); // only the list
  });

  it("uploads with the HR sharing choice, announces the version and reloads", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(res(list([])))
      .mockResolvedValueOnce(res(version({ visibility: "private" }), 201))
      .mockResolvedValueOnce(res(list([version({ visibility: "private" })])));
    vi.stubGlobal("fetch", fetchMock);
    render(<StudentResumeCard url={URL} />);
    fireEvent.change(await screen.findByLabelText("Upload resume"), { target: { files: [file(100)] } });
    fireEvent.click(screen.getByLabelText("Share with HR"));
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Resume version 1 uploaded.");
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe(URL);
    expect(init.method).toBe("POST");
    expect((init.body as FormData).get("visibility")).toBe("private");
    await screen.findByRole("link", { name: "Version 1 — Asha CV.pdf" });
  });

  it("shows the server's refusal and offers a retry when the list fails", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(res(list([])))
      .mockResolvedValueOnce(res({ detail: "Upload a PDF, DOC or DOCX file" }, 415));
    vi.stubGlobal("fetch", fetchMock);
    render(<StudentResumeCard url={URL} />);
    fireEvent.change(await screen.findByLabelText("Upload resume"), { target: { files: [file(100, "app.pdf")] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Upload a PDF, DOC or DOCX file");

    cleanup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res({}, 500)).mockResolvedValueOnce(res(list([]))));
    render(<StudentResumeCard url={URL} />);
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No resume uploaded yet.")).toBeInTheDocument();
  });
});

describe("ResumeLimitPanel (itc-026)", () => {
  it("validates the range and saves the limit", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(res({ max_mb: 5, max_bytes: 5 * MB, min_mb: 1, max_mb_ceiling: 10 }))
      .mockResolvedValueOnce(res({ max_mb: 2, max_bytes: 2 * MB, min_mb: 1, max_mb_ceiling: 10 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<ResumeLimitPanel />);
    const input = await screen.findByLabelText("Limit (MB)");
    expect(input).toHaveValue(5);
    fireEvent.change(input, { target: { value: "11" } });
    fireEvent.click(screen.getByRole("button", { name: "Set limit" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a whole number from 1 to 10.");
    fireEvent.change(input, { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Set limit" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Resume limit saved: 2 MB."));
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ max_mb: 2 });
    expect(screen.getByText(/now 2 MB/)).toBeInTheDocument();
  });
});
