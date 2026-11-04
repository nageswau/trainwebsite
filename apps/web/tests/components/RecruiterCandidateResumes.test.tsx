import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateResumes from "@/components/RecruiterCandidateResumes";

afterEach(cleanup);
beforeEach(() => {
  global.fetch = vi.fn();
});

const current = { qualification: null, experience_months: null, location: null };
const resume = { version: 1, file_name: "cv.pdf", content_type: "application/pdf", size_bytes: 1024, uploaded_by: null, created_at: "2026-11-04T05:00:00Z", preview_status: null };

function upload(name: string) {
  fireEvent.change(screen.getByLabelText(/Upload/), { target: { files: [new File(["x"], name)] } });
  fireEvent.click(screen.getByRole("button", { name: "Upload" }));
}

describe("RecruiterCandidateResumes (hrc-015)", () => {
  it("offers Preview and Download for every version and accepts DOC", () => {
    render(<RecruiterCandidateResumes candidateId="c1" resumes={[resume]} canUpload current={current} onUploaded={() => {}} onApplied={() => {}} />);
    expect(screen.getByRole("button", { name: "Preview resume version 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download resume version 1" })).toBeInTheDocument();
    expect(screen.getByText("PDF, DOC or DOCX, up to 5 MB")).toBeInTheDocument();
    expect(screen.getByLabelText(/Upload/)).toHaveAttribute("accept", expect.stringContaining("application/msword"));
  });

  it("does not open the extraction review for a DOC that is still being converted (QA-01)", async () => {
    vi.mocked(global.fetch).mockResolvedValue(new Response(JSON.stringify({ version: 2, content_type: "application/msword", file_name: "cv.doc", size_bytes: 9 }), { status: 201 }));
    render(<RecruiterCandidateResumes candidateId="c1" resumes={[resume]} canUpload current={current} onUploaded={() => {}} onApplied={() => {}} />);
    upload("cv.doc");
    expect(await screen.findByText("Resume version 2 uploaded. Its preview and extracted details will be ready in a moment.")).toBeInTheDocument();
    expect(screen.queryByText(/Review extracted details —/)).not.toBeInTheDocument();
    expect(vi.mocked(global.fetch)).toHaveBeenCalledTimes(1);
  });
});
