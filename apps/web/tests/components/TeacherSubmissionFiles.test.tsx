import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TeacherWorkspaceActions from "@/components/TeacherWorkspaceActions";

// nehn-024 (DEC-SCOPE-291 F7): the grading card lists a submission's uploaded files through the authorised download route.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const res = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
const submission = {
  id: "s1", assignment: "Week 1 scan", student: "Asha", answer: null, file_url: null, max_score: 100, status: "submitted",
  files: [{ id: "f1", filename: "Lösung 1.pdf", content_type: "application/pdf", size: 3 * 1024 * 1024, url: "/api/v1/workflows/it/submissions/s1/files/f1" }],
};

function serve(rows: unknown[]) {
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    if (String(url).includes("/trainer/context")) return Promise.resolve(res({ batches: [], students: [], enrollments: [] }));
    if (String(url).endsWith("/trainer/submissions")) return Promise.resolve(res(rows));
    return Promise.resolve(res([]));
  }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("TeacherWorkspaceActions grading card", () => {
  it("lists uploaded files as downloads", async () => {
    serve([submission]);
    render(<TeacherWorkspaceActions section="assignments" />);
    fireEvent.change(await screen.findByLabelText("Submitted work"), { target: { value: "s1" } });
    const link = await screen.findByRole("link", { name: "Download Lösung 1.pdf (3.0 MB)" });
    expect(link.getAttribute("href")).toBe("/api/v1/workflows/it/submissions/s1/files/f1");
    expect(screen.queryByText("Nothing was submitted.")).toBeNull();
  });

  it("still shows a link-only submission", async () => {
    serve([{ ...submission, files: [], file_url: "https://github.com/a/b" }]);
    render(<TeacherWorkspaceActions section="assignments" />);
    fireEvent.change(await screen.findByLabelText("Submitted work"), { target: { value: "s1" } });
    expect((await screen.findByRole("link", { name: "Open submitted file" })).getAttribute("href")).toBe("https://github.com/a/b");
  });
});
