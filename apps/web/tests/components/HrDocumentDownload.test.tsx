import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import HrDocumentDownload from "@/components/HrDocumentDownload";
import { classesParts } from "@/lib/hrStudents";
import { navForPermissions, PORTAL_NAV } from "@/lib/navigation";

const URL_UNDER_TEST = "/api/v1/hr/students/s1/documents/d1/download";

function stubFetch(response: { ok: boolean; status: number; body: unknown }) {
  const fetchMock = vi.fn(async () => ({ ok: response.ok, status: response.status, json: async () => response.body }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderButton() {
  render(<HrDocumentDownload studentId="s1" documentId="d1" name="cv.pdf" />);
  return screen.getByRole("button", { name: "Download cv.pdf" });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("HrDocumentDownload (nehn-017)", () => {
  it("opens the short-lived URL the API returns", async () => {
    const fetchMock = stubFetch({ ok: true, status: 200, body: { url: "/api/v1/files/signed/abc", expires_in: null } });
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    fireEvent.click(renderButton());
    await waitFor(() => expect(open).toHaveBeenCalledWith("/api/v1/files/signed/abc", "_blank", "noreferrer"));
    expect(fetchMock).toHaveBeenCalledWith(URL_UNDER_TEST, { cache: "no-store" });
  });

  it("is busy while the request runs, so a second click sends nothing", async () => {
    let finish: (value: unknown) => void = () => {};
    const fetchMock = vi.fn(() => new Promise((resolve) => { finish = resolve; }));
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "open").mockImplementation(() => null);
    const button = renderButton();
    fireEvent.click(button);
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent("Opening…");
    fireEvent.click(button);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    finish({ ok: true, status: 200, json: async () => ({ url: "/x" }) });
    await waitFor(() => expect(button).not.toBeDisabled());
  });

  it("shows the API's refusal next to the button and opens nothing", async () => {
    stubFetch({ ok: false, status: 403, body: { detail: "This document type is not open to HR" } });
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    fireEvent.click(renderButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("This document type is not open to HR");
    expect(open).not.toHaveBeenCalled();
  });

  it("says so when the network fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("network"); }));
    fireEvent.click(renderButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't open the document. Please try again.");
  });
});

describe("classesParts (nehn-017 QA17-02, QA17-05)", () => {
  it("names each status and the classes marked, as parts a narrow cell wraps between", () => {
    expect(classesParts({ marked: 12, present: 10, late: 0, excused: 0, absent: 2, attendance_pct: 83.33 })).toEqual(["Present 10", "Late 0", "Excused 0", "Absent 2 (12 marked)"]);
  });
  it("says none were marked instead of zeros", () => {
    expect(classesParts({ marked: 0, present: 0, late: 0, excused: 0, absent: 0, attendance_pct: null })).toEqual(["No classes marked yet"]);
  });
});

describe("HR nav (nehn-017)", () => {
  const nav = PORTAL_NAV["it/hr"];
  it("adds Students, Reports and the Report library, keeping the existing items", () => {
    const hrefs = nav.map((item) => item.href);
    expect(hrefs).toEqual(expect.arrayContaining(["/it/hr/dashboard", "/it/hr/students", "/it/hr/reports", "/it/hr/report-library", "/recruiter/candidates"]));
  });
  it("hides Students when student_progress.view is revoked", () => {
    expect(navForPermissions(nav, []).map((item) => item.href)).not.toContain("/it/hr/students");
    expect(navForPermissions(nav, ["student_progress.view"]).map((item) => item.href)).toContain("/it/hr/students");
  });
});
