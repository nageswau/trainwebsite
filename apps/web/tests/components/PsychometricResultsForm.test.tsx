import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PsychometricResultsForm from "@/components/PsychometricResultsForm";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const RECORD = { id: "r1", assessment_type: "Aptitude Test", strengths: ["Logic", "Verbal"], counsellor_remarks: "Keep going", test_date: "2026-09-10" };
const ok = () => vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: "r1" }) });

function renderForm(onDone = vi.fn()) {
  render(<PsychometricResultsForm record={RECORD} studentName="Asha" onDone={onDone} />);
  return onDone;
}

describe("PsychometricResultsForm", () => {
  it("focuses its heading and prefills every field", () => {
    renderForm();
    expect(screen.getByRole("heading", { name: "Results — Asha · Aptitude Test" })).toHaveFocus();
    expect(screen.getByLabelText("Strengths")).toHaveValue("Logic, Verbal");
    expect(screen.getByLabelText("Test date")).toHaveValue("2026-09-10");
    expect(screen.getByLabelText("Counsellor remarks")).toHaveValue("Keep going");
    expect(screen.getByLabelText("Interest areas")).toHaveValue("");
  });

  it("sends only the changed fields, emptied ones as null", async () => {
    const fetchMock = ok();
    vi.stubGlobal("fetch", fetchMock);
    const onDone = renderForm();
    fireEvent.change(screen.getByLabelText("Strengths"), { target: { value: "Logic, Verbal, Spatial" } });
    fireEvent.change(screen.getByLabelText("Counsellor remarks"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save results" }));
    await vi.waitFor(() => expect(onDone).toHaveBeenCalledWith(true));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/school/psychometric-team/records/r1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ strengths: ["Logic", "Verbal", "Spatial"], counsellor_remarks: null });
  });

  it("sends nothing when nothing changed", () => {
    const fetchMock = ok();
    vi.stubGlobal("fetch", fetchMock);
    renderForm();
    fireEvent.click(screen.getByRole("button", { name: "Save results" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("No changes to save.");
  });

  it("clears an earlier status when a later save is blocked by a field error (QA27-01)", () => {
    vi.stubGlobal("fetch", ok());
    renderForm();
    fireEvent.click(screen.getByRole("button", { name: "Save results" }));
    expect(screen.getByRole("status")).toHaveTextContent("No changes to save.");
    fireEvent.change(screen.getByLabelText("Strengths"), { target: { value: "y".repeat(81) } });
    fireEvent.click(screen.getByRole("button", { name: "Save results" }));
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByLabelText("Strengths")).toHaveAttribute("aria-invalid", "true");
  });

  it("blocks an over-long list item on the client, marks the field and focuses it", () => {
    const fetchMock = ok();
    vi.stubGlobal("fetch", fetchMock);
    renderForm();
    const field = screen.getByLabelText("Interest areas");
    fireEvent.change(field, { target: { value: "x".repeat(81) } });
    fireEvent.click(screen.getByRole("button", { name: "Save results" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveAccessibleDescription(/80 characters or fewer/);
    expect(field).toHaveFocus();
  });

  it("refuses a half-typed date instead of silently clearing it (final review)", () => {
    const fetchMock = ok();
    vi.stubGlobal("fetch", fetchMock);
    renderForm();
    const field = screen.getByLabelText("Test date");
    // A partly typed <input type="date"> reports value "" with validity.badInput set; jsdom cannot type one, so stub it.
    Object.defineProperty(field, "validity", { value: { badInput: true } });
    fireEvent.change(field, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save results" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveAccessibleDescription(/complete date/i);
    expect(field).toHaveFocus();
  });

  it("keeps the card open with the input on a failed save", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: "This school's partnership expired on 22 Sep 2026." }) }));
    const onDone = renderForm();
    fireEvent.change(screen.getByLabelText("Recommended streams"), { target: { value: "Commerce" } });
    fireEvent.click(screen.getByRole("button", { name: "Save results" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("partnership expired");
    expect(onDone).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Recommended streams")).toHaveValue("Commerce");
    expect(screen.getByRole("button", { name: "Save results" })).toBeEnabled();
  });

  it("tells the user their entry is kept when the server fails (QA27-03)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => { throw new Error("not json"); } }));
    renderForm();
    fireEvent.change(screen.getByLabelText("Interest areas"), { target: { value: "Music" } });
    fireEvent.click(screen.getByRole("button", { name: "Save results" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side. Your entry is kept — try again in a moment.");
    expect(screen.getByLabelText("Interest areas")).toHaveValue("Music");
  });

  it("offers a sign-in link in a new tab when the session has ended, keeping the entry (QA27-04)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({ detail: "Not authenticated" }) }));
    renderForm();
    fireEvent.change(screen.getByLabelText("Interest areas"), { target: { value: "Music" } });
    fireEvent.click(screen.getByRole("button", { name: "Save results" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Your session has ended. Sign in again in a new tab, then press Save here — your entry is kept.");
    const link = screen.getByRole("link", { name: "Sign in again (opens a new tab)" });
    expect(link).toHaveAttribute("href", "/overseas/login");
    expect(link).toHaveAttribute("target", "_blank");
    expect(screen.getByLabelText("Interest areas")).toHaveValue("Music");
  });

  it("disables both buttons while saving", async () => {
    let resolve: (v: unknown) => void = () => {};
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise((r) => { resolve = r; })));
    renderForm();
    fireEvent.change(screen.getByLabelText("Follow-up date"), { target: { value: "2026-10-15" } });
    fireEvent.click(screen.getByRole("button", { name: "Save results" }));
    expect(await screen.findByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    resolve({ ok: true, status: 200, json: async () => ({}) });
  });

  it("warns before leaving only while there are unsaved changes, and Cancel reports not saved", () => {
    const add = vi.spyOn(window, "addEventListener");
    const onDone = renderForm();
    expect(add.mock.calls.some(([type]) => type === "beforeunload")).toBe(false);
    fireEvent.change(screen.getByLabelText("Strengths"), { target: { value: "Logic" } });
    expect(add.mock.calls.some(([type]) => type === "beforeunload")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onDone).toHaveBeenCalledWith(false);
  });

  it("tells the user how to keep a comma inside one item (commas separate items)", () => {
    renderForm();
    expect(screen.getByLabelText("Recommended streams")).toHaveAccessibleDescription(/use \/ or ; inside an item/i);
  });

  it("asks before an in-app link discards unsaved results, and stays on 'no' (QA27-02)", () => {
    const link = document.body.appendChild(Object.assign(document.createElement("a"), { href: "/account/profile", textContent: "My profile" }));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderForm();
    const click = () => { const e = new MouseEvent("click", { bubbles: true, cancelable: true }); link.dispatchEvent(e); return e; };
    expect(click().defaultPrevented).toBe(false); // nothing typed yet: no prompt
    expect(confirm).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Strengths"), { target: { value: "Logic" } });
    expect(click().defaultPrevented).toBe(true); // "no" keeps the user here
    expect(confirm).toHaveBeenCalledWith("Leave without saving your results?");
    confirm.mockReturnValue(true);
    expect(click().defaultPrevented).toBe(false); // "yes" lets the navigation happen
    link.remove();
  });

  it("shows a character count for the remarks", () => {
    renderForm();
    expect(screen.getByText("10 / 4000")).toBeTruthy();
  });
});
