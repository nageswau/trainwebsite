import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ReportDownloadButton from "@/components/ReportDownloadButton";

const URL_UNDER_TEST = "/api/v1/school/reports/school-summary";
const clicked: { href: string; download: string }[] = [];

function pdfResponse() {
  return { ok: true, status: 200, headers: new Headers({ "content-type": "application/pdf" }), blob: async () => new Blob(["%PDF-1.4"], { type: "application/pdf" }), json: async () => ({}) };
}

function errorResponse(status: number, body: unknown, contentType = "application/json") {
  return { ok: false, status, headers: new Headers({ "content-type": contentType }), blob: async () => new Blob([]), json: async () => body };
}

function renderButton() {
  render(<ReportDownloadButton url={URL_UNDER_TEST} label="Download school report (PDF)" filename="school-report.pdf" />);
  return screen.getByRole("button", { name: "Download school report (PDF)" });
}

beforeEach(() => {
  clicked.length = 0;
  URL.createObjectURL = vi.fn(() => "blob:report");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    clicked.push({ href: this.getAttribute("href") ?? "", download: this.download });
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ReportDownloadButton (ENH-015)", () => {
  // QA15-10: the PDF is untagged, so the button says where the same information can be read with a screen reader.
  it("shows its hint and ties it to the button", () => {
    render(<ReportDownloadButton url={URL_UNDER_TEST} label="Download school report (PDF)" filename="school-report.pdf" hint="The same figures are on this page." />);
    const button = screen.getByRole("button", { name: "Download school report (PDF)" });
    expect(button).toHaveAccessibleDescription("The same figures are on this page.");
    expect(screen.getByText("The same figures are on this page.")).toHaveClass("field-hint");
  });

  it("renders no description without a hint", () => {
    expect(renderButton()).not.toHaveAttribute("aria-describedby");
  });

  it("downloads the PDF under its filename, announces it and frees the object URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(pdfResponse());
    vi.stubGlobal("fetch", fetchMock);
    fireEvent.click(renderButton());
    expect(await screen.findByRole("status")).toHaveTextContent("Report downloaded.");
    expect(fetchMock).toHaveBeenCalledWith(URL_UNDER_TEST, { credentials: "same-origin" });
    expect(clicked).toEqual([{ href: "blob:report", download: "school-report.pdf" }]);
    await vi.waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:report"));
  });

  it("shows a busy state and ignores a second click while preparing", async () => {
    let finish: (value: unknown) => void = () => {};
    const fetchMock = vi.fn(() => new Promise((resolve) => { finish = resolve; }));
    vi.stubGlobal("fetch", fetchMock);
    const button = renderButton();
    fireEvent.click(button);
    fireEvent.click(button);
    const busy = screen.getByRole("button", { name: "Preparing PDF…" });
    expect(busy).toHaveAttribute("aria-disabled", "true");
    expect(busy).toHaveAttribute("aria-busy", "true");
    fireEvent.click(busy);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    finish(pdfResponse());
    expect(await screen.findByRole("status")).toHaveTextContent("Report downloaded.");
    expect(screen.getByRole("button", { name: "Download school report (PDF)" })).toHaveAttribute("aria-disabled", "false");
  });

  it("keeps keyboard focus on the button through a download (QA15-01)", async () => {
    let finish: (value: unknown) => void = () => {};
    vi.stubGlobal("fetch", vi.fn(() => new Promise((resolve) => { finish = resolve; })));
    const button = renderButton();
    button.focus();
    fireEvent.click(button);
    // `disabled` would drop focus to <body>; the busy state must not.
    expect(button).not.toBeDisabled();
    expect(button).toHaveFocus();
    finish(pdfResponse());
    expect(await screen.findByRole("status")).toHaveTextContent("Report downloaded.");
    expect(button).toHaveFocus();
  });

  it("asks the user to sign in again when the session has expired", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(errorResponse(401, { detail: "Not authenticated" })));
    fireEvent.click(renderButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("Your session has expired. Sign in again.");
  });

  it("shows the server's reason for a refusal", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(errorResponse(403, { detail: "This student is not linked to your account" })));
    fireEvent.click(renderButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("This student is not linked to your account");
  });

  it("shows the server's reason for a missing student", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(errorResponse(404, { detail: "Student not found" })));
    fireEvent.click(renderButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("Student not found");
  });

  it("words a server error for people and lets them retry", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(errorResponse(500, "Internal Server Error", "text/plain")).mockResolvedValueOnce(pdfResponse());
    vi.stubGlobal("fetch", fetchMock);
    fireEvent.click(renderButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side. Please try again.");
    fireEvent.click(screen.getByRole("button", { name: "Download school report (PDF)" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Report downloaded.");
  });

  it("treats a dropped connection as a retryable failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    fireEvent.click(renderButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side. Please try again.");
    expect(screen.getByRole("button", { name: "Download school report (PDF)" })).toBeEnabled();
  });

  it("never saves a 200 that is not a PDF (e.g. a proxy login page)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ...pdfResponse(), headers: new Headers({ "content-type": "text/html" }) }));
    fireEvent.click(renderButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side. Please try again.");
    expect(clicked).toEqual([]);
  });
});

describe("ReportDownloadButton CSV (AGN-014)", () => {
  function csvResponse() {
    return { ok: true, status: 200, headers: new Headers({ "content-type": "text/csv; charset=utf-8" }), blob: async () => new Blob(["a,b"]), json: async () => ({}) };
  }

  it("saves a CSV when told to expect one, with its own busy label", async () => {
    let finish: (value: unknown) => void = () => {};
    vi.stubGlobal("fetch", vi.fn(() => new Promise((resolve) => { finish = resolve; })));
    render(<ReportDownloadButton url="/x.csv" label="Download CSV" filename="x.csv" contentType="text/csv" busyLabel="Preparing CSV…" />);
    fireEvent.click(screen.getByRole("button", { name: "Download CSV" }));
    expect(screen.getByRole("button", { name: "Preparing CSV…" })).toBeInTheDocument();
    finish(csvResponse());
    expect(await screen.findByRole("status")).toHaveTextContent("Report downloaded.");
    expect(clicked).toEqual([{ href: "blob:report", download: "x.csv" }]);
  });

  it("still refuses a CSV when expecting the default PDF", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(csvResponse()));
    fireEvent.click(renderButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side. Please try again.");
    expect(clicked).toEqual([]);
  });
});
