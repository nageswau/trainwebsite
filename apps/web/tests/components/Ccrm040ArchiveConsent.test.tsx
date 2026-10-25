import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OverseasConsentCard from "@/components/OverseasConsentCard";
import StudentArchiveControls from "@/components/StudentArchiveControls";
import StudentMessages from "@/components/StudentMessages";
import type { MyConsent } from "@/lib/overseasConsents";

// ccrm-040 (DEC-SCOPE-275): the 360's archive controls (AR1-AR7), the student's consent card (CN2/CN3) and ccrm-037's WhatsApp
// opt-in reason (CN7).
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  refresh.mockReset();
  fetchMock = vi.fn(() => Promise.resolve(res({})));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const archived = { archived_at: "2026-10-25T06:00:00Z", archived_by: "Nora Counselor", reason: "Studies finished" };

describe("StudentArchiveControls (ccrm-040 AR)", () => {
  it("archives with a reason and refreshes the page", async () => {
    render(<StudentArchiveControls studentId="S1" archive={null} permissions={{ archive: true, restore: false }} />);
    fireEvent.click(screen.getByRole("button", { name: "Archive student" }));
    fireEvent.click(screen.getByRole("button", { name: "Archive student" }));
    expect((await screen.findByRole("alert")).textContent).toContain("at least 3 characters");
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "  Studies finished " } });
    fireEvent.click(screen.getByRole("button", { name: "Archive student" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/counselor/students/S1/archive");
    expect(JSON.parse(init.body)).toEqual({ reason: "Studies finished" });
  });

  it("shows the server's refusal and keeps the form", async () => {
    fetchMock.mockResolvedValueOnce(res({ detail: "Close or withdraw the student's open applications first: APP-000001" }, 409));
    render(<StudentArchiveControls studentId="S1" archive={null} permissions={{ archive: true, restore: false }} />);
    fireEvent.click(screen.getByRole("button", { name: "Archive student" }));
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "Done" } });
    fireEvent.click(screen.getByRole("button", { name: "Archive student" }));
    expect((await screen.findByRole("alert")).textContent).toContain("APP-000001");
    expect(screen.getByLabelText("Reason")).toBeTruthy();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("offers nothing to a reader who may not archive", () => {
    const { container } = render(<StudentArchiveControls studentId="S1" archive={null} permissions={{ archive: false, restore: false }} />);
    expect(container.textContent).toBe("");
  });

  it("shows the archived banner; only the Admin restores", async () => {
    render(<StudentArchiveControls studentId="S1" archive={archived} permissions={{ archive: false, restore: false }} />);
    expect(screen.getByRole("status").textContent).toContain("Reason: Studies finished");
    expect(screen.queryByRole("button", { name: "Restore student" })).toBeNull();
    cleanup();
    render(<StudentArchiveControls studentId="S1" archive={archived} permissions={{ archive: false, restore: true }} />);
    fireEvent.click(screen.getByRole("button", { name: "Restore student" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/counselor/students/S1/restore");
  });
});

const consent = (over: Partial<MyConsent>): MyConsent => ({ id: "C1", kind: "data_processing", title: "Consent to process my personal data", body: "I agree…", version: "v1", accepted_at: null, ...over });

describe("OverseasConsentCard (ccrm-040 CN2/CN3)", () => {
  const items = [consent({}), consent({ id: "C2", kind: "document_sharing", title: "Consent to share my documents" })];

  it("asks for each pending consent and records the ticked ones", async () => {
    render(<OverseasConsentCard items={items} />);
    expect(screen.getByRole("heading", { name: "Your consent" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Save consent" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Tick at least one");
    fireEvent.click(screen.getAllByRole("checkbox", { name: "I agree" })[1]);
    fireEvent.click(screen.getByRole("button", { name: "Save consent" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(fetchMock.mock.calls.map((c) => c[0])).toEqual(["/api/v1/overseas/me/consents/C2/accept"]);
    expect(screen.getByRole("link", { name: "your notification preferences" }).getAttribute("href")).toBe("/account/profile");
  });

  it("shows only what is still to give, and nothing once everything is given", () => {
    render(<OverseasConsentCard items={[consent({ accepted_at: "2026-10-25T06:00:00Z" }), items[1]]} />);
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    expect(screen.queryByText("Consent to process my personal data")).toBeNull();
    cleanup();
    const { container } = render(<OverseasConsentCard items={[consent({ accepted_at: "2026-10-25T06:00:00Z" })]} />);
    expect(container.textContent).toBe("");
  });
});

describe("StudentMessages WhatsApp opt-in (ccrm-040 CN7)", () => {
  it("says the student has not opted in instead of 'no number'", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(res({ items: [], total: 0, limit: 50, offset: 0 })));
    render(<StudentMessages studentId="S1" recipient={{ name: "Priya Student", email: "p@example.com", whatsapp_to: null, whatsapp_opt_in: false }} applications={[]} canWrite />);
    expect(await screen.findByText("Priya Student has not opted in to WhatsApp messages.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Send WhatsApp" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
