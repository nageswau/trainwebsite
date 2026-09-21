import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolIncomingTransferForm, { NEUTRAL_SUBMITTED } from "@/components/SchoolIncomingTransferForm";

// ENH-005 -- a coordinator asks for a student at ANOTHER school by Student ID (spec §5.2, §7.1, security review S3).
// The screen must say the same thing for every well-formed code, so it never confirms whether a student exists.
const json = (body: unknown, status = 200, headers: Record<string, string> = {}) => new Response(JSON.stringify(body), { status, headers });

function stubFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const fn = vi.fn((url: string, init?: RequestInit) => Promise.resolve(handler(String(url), init)));
  vi.stubGlobal("fetch", fn);
  return fn;
}

const input = () => screen.getByLabelText("Student ID") as HTMLInputElement;
const submit = () => fireEvent.click(screen.getByRole("button", { name: /Request student/ }));
const type = (value: string) => fireEvent.change(input(), { target: { value } });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SchoolIncomingTransferForm", () => {
  it("labels the field, limits it to 8 characters and turns off autofill and spellcheck", () => {
    render(<SchoolIncomingTransferForm />);
    expect(input().maxLength).toBe(8);
    expect(input().getAttribute("autocomplete")).toBe("off");
    expect(input().getAttribute("spellcheck")).toBe("false");
  });

  it("rejects a malformed code on the client with a field-tied message and sends nothing", () => {
    const fetchMock = stubFetch(() => json({ accepted: true }, 202));
    render(<SchoolIncomingTransferForm />);
    type("XYZ");
    submit();
    expect(input().getAttribute("aria-invalid")).toBe("true");
    const message = screen.getByText(/8 characters/);
    expect(input().getAttribute("aria-describedby")).toContain(message.id);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends the trimmed, upper-cased code as JSON", async () => {
    const fetchMock = stubFetch(() => json({ accepted: true }, 202));
    render(<SchoolIncomingTransferForm />);
    type(" a3f9c21b ");
    submit();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/school/transfer-requests/incoming");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ student_code: "A3F9C21B" });
  });

  it("gives the identical neutral message for every accepted code, then clears and refocuses the field", async () => {
    stubFetch(() => json({ accepted: true }, 202));
    const onSubmitted = vi.fn();
    render(<SchoolIncomingTransferForm onSubmitted={onSubmitted} />);
    const seen: string[] = [];
    for (const code of ["A3F9C21B", "00000000"]) {
      type(code);
      submit();
      const status = await screen.findByRole("status");
      await waitFor(() => expect(status.textContent).toBe(NEUTRAL_SUBMITTED));
      seen.push(status.textContent ?? "");
      expect(input().value).toBe("");
      await waitFor(() => expect(document.activeElement).toBe(input())); // refocus() runs after the re-enable render
    }
    expect(new Set(seen).size).toBe(1);
    expect(NEUTRAL_SUBMITTED).not.toMatch(/found|exists|unknown|invalid|no student/i);
    expect(onSubmitted).toHaveBeenCalledTimes(2);
  });

  it("blocks a double submit and says it is sending", async () => {
    let release!: (r: Response) => void;
    const fetchMock = stubFetch(() => new Promise<Response>((resolve) => (release = resolve)) as unknown as Response);
    render(<SchoolIncomingTransferForm />);
    type("A3F9C21B");
    submit();
    const busy = await screen.findByRole("button", { name: "Sending request…" });
    expect((busy as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(busy);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    release(json({ accepted: true }, 202));
    await screen.findByRole("status");
  });

  it("shows the server's message for the open-request cap (409) in an alert that takes focus", async () => {
    stubFetch(() => json({ detail: "Too many open transfer requests; wait for a decision or cancel one" }, 409));
    render(<SchoolIncomingTransferForm />);
    type("A3F9C21B");
    submit();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Too many open transfer requests");
    await waitFor(() => expect(document.activeElement).toBe(alert));
    expect(input().value).toBe("A3F9C21B"); // kept so it can be retried
  });

  it("says when to try again for the filing throttle (429)", async () => {
    stubFetch(() => json({ detail: "Too many transfer requests; try again in 90 seconds" }, 429, { "Retry-After": "90" }));
    render(<SchoolIncomingTransferForm />);
    type("A3F9C21B");
    submit();
    expect((await screen.findByRole("alert")).textContent).toContain("try again in 90 seconds");
  });

  it("offers to sign in again when the session has expired (401)", async () => {
    stubFetch(() => json({ detail: "Not authenticated" }, 401));
    render(<SchoolIncomingTransferForm />);
    type("A3F9C21B");
    submit();
    expect((await screen.findByRole("link", { name: "Sign in again" })).getAttribute("href")).toBe("/overseas/login");
  });

  it("reports a network failure without losing the code", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
    render(<SchoolIncomingTransferForm />);
    type("A3F9C21B");
    submit();
    expect((await screen.findByRole("alert")).textContent).toMatch(/did not complete/i);
    expect(input().value).toBe("A3F9C21B");
  });

  it("sends ONE request when two clicks arrive before React has re-rendered", async () => {
    const fetchMock = stubFetch(() => json({ accepted: true }, 202));
    render(<SchoolIncomingTransferForm />);
    type("A3F9C21B");
    const button = screen.getByRole("button", { name: /Request student/ });
    act(() => {
      button.click();
      button.click();
    });
    await screen.findByRole("status");
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe(NEUTRAL_SUBMITTED));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
