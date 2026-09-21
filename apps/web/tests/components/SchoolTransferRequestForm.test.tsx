import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolTransferRequestForm from "@/components/SchoolTransferRequestForm";

// ENH-005 -- a coordinator asks to move ONE of their students to another school (spec §5.2, §7.1).
const { refresh } = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const SCHOOLS = [{ id: "b", name: "Lakeview School" }, { id: "c", name: "Hillcrest School" }];
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function stubFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const fn = vi.fn((url: string, init?: RequestInit) => Promise.resolve(handler(String(url), init)));
  vi.stubGlobal("fetch", fn);
  return fn;
}

const select = () => screen.getByLabelText("Destination school") as HTMLSelectElement;
const submit = () => fireEvent.click(screen.getByRole("button", { name: /Request transfer|Sending request/ }));

afterEach(() => {
  cleanup();
  refresh.mockReset();
  vi.unstubAllGlobals();
});

describe("SchoolTransferRequestForm", () => {
  it("says so, and offers no form, when there is no other school", () => {
    render(<SchoolTransferRequestForm studentId="s1" destinations={[]} pending={null} />);
    expect(screen.getByText("No other partner schools are available.")).toBeTruthy();
    expect(screen.queryByLabelText("Destination school")).toBeNull();
  });

  it("keeps a failed destinations load visible", () => {
    render(<SchoolTransferRequestForm studentId="s1" destinations={null} pending={null} />);
    expect(screen.getByText("Transfers are unavailable right now.")).toBeTruthy();
  });

  it("replaces the form with the pending request's state", () => {
    render(<SchoolTransferRequestForm studentId="s1" destinations={SCHOOLS} pending={{ to_school_name: "Lakeview School", created_at: "2026-09-21T10:00:00Z" }} />);
    const status = screen.getByRole("status");
    expect(status.textContent).toMatch(/Transfer to Lakeview School requested/);
    expect(status.textContent).toMatch(/Waiting for admin review/);
    expect(screen.queryByLabelText("Destination school")).toBeNull();
  });

  it("labels its fields and starts on a disabled placeholder", () => {
    render(<SchoolTransferRequestForm studentId="s1" destinations={SCHOOLS} pending={null} />);
    expect(select().value).toBe("");
    expect(screen.getByLabelText(/Reason/)).toBeTruthy();
    expect((screen.getByRole("option", { name: "Select a school" }) as HTMLOptionElement).disabled).toBe(true);
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Select a school", "Lakeview School", "Hillcrest School"]);
  });

  it("asks for a destination on the client and sends nothing", () => {
    const fetchMock = stubFetch(() => json({}, 201));
    render(<SchoolTransferRequestForm studentId="s1" destinations={SCHOOLS} pending={null} />);
    submit();
    expect(select().getAttribute("aria-invalid")).toBe("true");
    const message = screen.getByText("Choose a school.");
    expect(select().getAttribute("aria-describedby")).toContain(message.id);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends only the destination and reason, then confirms and refreshes", async () => {
    const fetchMock = stubFetch(() => json({ id: "r1" }, 201));
    render(<SchoolTransferRequestForm studentId="s1" destinations={SCHOOLS} pending={null} />);
    fireEvent.change(select(), { target: { value: "b" } });
    fireEvent.change(screen.getByLabelText(/Reason/), { target: { value: "  Family is moving " } });
    submit();

    const status = await screen.findByText(/Transfer request sent/);
    expect(status.closest("[role=status]")).toBeTruthy();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/school/students/s1/transfer-requests");
    expect(JSON.parse(String(init?.body))).toEqual({ to_school_id: "b", reason: "Family is moving" });
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(screen.queryByLabelText("Destination school")).toBeNull(); // shown as pending now, not asked again
  });

  it("omits an empty reason and blocks a double submit while sending", async () => {
    let release!: (r: Response) => void;
    const fetchMock = stubFetch(() => new Promise<Response>((resolve) => (release = resolve)) as unknown as Response);
    render(<SchoolTransferRequestForm studentId="s1" destinations={SCHOOLS} pending={null} />);
    fireEvent.change(select(), { target: { value: "c" } });
    submit();
    const busy = await screen.findByRole("button", { name: "Sending request…" });
    expect((busy as HTMLButtonElement).disabled).toBe(true);
    expect(select().disabled).toBe(true);
    fireEvent.click(busy);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ to_school_id: "c" });
    release(json({ id: "r1" }, 201));
    await screen.findByText(/Transfer request sent/);
  });

  it("shows a server refusal in an alert that takes focus and keeps the form for a retry", async () => {
    stubFetch(() => json({ detail: "A transfer request is already pending for this student" }, 409));
    render(<SchoolTransferRequestForm studentId="s1" destinations={SCHOOLS} pending={null} />);
    fireEvent.change(select(), { target: { value: "b" } });
    submit();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("already pending");
    await waitFor(() => expect(document.activeElement).toBe(alert));
    expect(select().value).toBe("b");
  });

  it("joins FastAPI's 422 messages, offers sign-in on 401, and survives a network failure", async () => {
    stubFetch(() => json({ detail: [{ msg: "Field required" }, { msg: "Invalid input" }] }, 422));
    render(<SchoolTransferRequestForm studentId="s1" destinations={SCHOOLS} pending={null} />);
    fireEvent.change(select(), { target: { value: "b" } });
    submit();
    expect((await screen.findByRole("alert")).textContent).toContain("Field required; Invalid input");
    cleanup();

    stubFetch(() => json({ detail: "Not authenticated" }, 401));
    render(<SchoolTransferRequestForm studentId="s1" destinations={SCHOOLS} pending={null} />);
    fireEvent.change(select(), { target: { value: "b" } });
    submit();
    expect((await screen.findByRole("link", { name: "Sign in again" })).getAttribute("href")).toBe("/overseas/login");
    cleanup();

    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
    render(<SchoolTransferRequestForm studentId="s1" destinations={SCHOOLS} pending={null} />);
    fireEvent.change(select(), { target: { value: "b" } });
    submit();
    expect((await screen.findByRole("alert")).textContent).toMatch(/did not complete/i);
  });

  it("keeps the destination select inside the page however long a school's name is", () => {
    render(<SchoolTransferRequestForm studentId="s1" destinations={[{ id: "x", name: "N".repeat(400) }]} pending={null} />);
    // A <select> sizes itself to its longest option, which pushed the student page to 2,600px wide in a 1,424px window.
    expect(select().style.maxWidth).toBe("100%");
  });

  it("sends ONE request when two clicks arrive before React has re-rendered (found by the browser QA)", async () => {
    const fetchMock = stubFetch(() => json({ id: "r1" }, 201));
    render(<SchoolTransferRequestForm studentId="s1" destinations={SCHOOLS} pending={null} />);
    fireEvent.change(select(), { target: { value: "b" } });
    const button = screen.getByRole("button", { name: "Request transfer" });
    act(() => {
      button.click();
      button.click(); // same task: the busy state from the first click has not been rendered yet
    });
    await screen.findByText(/Transfer request sent/);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
