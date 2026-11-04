import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DocumentFileActions from "@/components/DocumentFileActions";

afterEach(cleanup);
const assign = vi.fn();
beforeEach(() => {
  global.fetch = vi.fn();
  assign.mockReset();
  Object.defineProperty(window, "location", { value: { ...window.location, assign }, writable: true });
});

const ok = (url: string) => new Response(JSON.stringify({ url, expires_in: 300 }), { status: 200 });
const fail = (status: number, detail: string) => new Response(JSON.stringify({ detail }), { status });
const LINK = "/api/v1/recruiter/candidates/c1/resume/2/link";

describe("DocumentFileActions (hrc-015)", () => {
  it("downloads through a fresh signed link", async () => {
    vi.mocked(global.fetch).mockResolvedValue(ok("/api/v1/files/signed/abc"));
    render(<DocumentFileActions linkUrl={LINK} contentType="application/pdf" label="Version 2" />);
    fireEvent.click(screen.getByRole("button", { name: "Download Version 2" }));
    await vi.waitFor(() => expect(assign).toHaveBeenCalledWith("/api/v1/files/signed/abc"));
    expect(vi.mocked(global.fetch).mock.calls[0][0]).toBe(`${LINK}?mode=download`);
  });

  it("previews a PDF in a labelled frame and closes it", async () => {
    vi.mocked(global.fetch).mockResolvedValue(ok("/api/v1/files/signed/pdf"));
    render(<DocumentFileActions linkUrl={LINK} contentType="application/msword" label="Version 2" />);
    fireEvent.click(screen.getByRole("button", { name: "Preview Version 2" }));
    const frame = await screen.findByTitle("Preview of Version 2");
    expect(frame.tagName).toBe("IFRAME");
    expect(frame).toHaveAttribute("src", "/api/v1/files/signed/pdf");
    expect(vi.mocked(global.fetch).mock.calls[0][0]).toBe(`${LINK}?mode=preview`);
    fireEvent.click(screen.getByRole("button", { name: "Close preview" }));
    expect(screen.queryByTitle("Preview of Version 2")).not.toBeInTheDocument();
  });

  it("shows an image inline", async () => {
    vi.mocked(global.fetch).mockResolvedValue(ok("/api/v1/files/signed/png"));
    render(<DocumentFileActions linkUrl={LINK} contentType="image/png" label="AWS certificate" />);
    fireEvent.click(screen.getByRole("button", { name: "Preview AWS certificate" }));
    expect(await screen.findByRole("img", { name: "Preview of AWS certificate" })).toHaveAttribute("src", "/api/v1/files/signed/png");
  });

  it("says a preview is being prepared and checks again", async () => {
    vi.mocked(global.fetch)
      .mockResolvedValueOnce(fail(409, "The preview is still being prepared. Try again in a moment."))
      .mockResolvedValueOnce(ok("/api/v1/files/signed/ready"));
    render(<DocumentFileActions linkUrl={LINK} contentType="application/msword" label="Version 2" />);
    fireEvent.click(screen.getByRole("button", { name: "Preview Version 2" }));
    expect(await screen.findByText("The preview is still being prepared. Try again in a moment.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    expect(await screen.findByTitle("Preview of Version 2")).toBeInTheDocument();
  });

  it("explains when no preview exists and keeps Download", async () => {
    vi.mocked(global.fetch).mockResolvedValue(fail(422, "A preview isn't available for this file. Download it instead."));
    render(<DocumentFileActions linkUrl={LINK} contentType="application/msword" label="Version 2" />);
    fireEvent.click(screen.getByRole("button", { name: "Preview Version 2" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A preview isn't available for this file. Download it instead.");
    expect(screen.queryByRole("button", { name: "Check again" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download Version 2" })).toBeEnabled();
  });

  it("reports a failed download without leaving the page", async () => {
    vi.mocked(global.fetch).mockRejectedValue(new TypeError("offline"));
    render(<DocumentFileActions linkUrl={LINK} contentType="application/pdf" label="Version 2" />);
    fireEvent.click(screen.getByRole("button", { name: "Download Version 2" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't open the file. Check your connection and try again.");
    expect(assign).not.toHaveBeenCalled();
  });
});
