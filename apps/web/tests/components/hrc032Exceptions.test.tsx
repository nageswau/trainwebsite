import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DeliveryExceptionsPanel from "@/components/DeliveryExceptionsPanel";
import { type ExceptionPage, type ExceptionRow, listUrl, pageHref, parseFilters, retryUrl } from "@/lib/notificationExceptions";

// hrc-032 (DEC-SCOPE-413 N8/N9): the Delivery exceptions page -- what a row shows, its Retry, and the empty and error states.
const ROW: ExceptionRow = {
  source: "delivery", id: "d1", type: "it.requirement.changed", type_label: "Vacancy updated", recipient: "Asha Rao", channel: "whatsapp",
  error: "provider down", attempts: 4, failed_at: "2026-11-06T10:00:00Z",
};
const page = (items: ExceptionRow[], total = items.length): ExceptionPage => ({
  items, total, limit: 50, offset: 0, types: [{ key: "it.requirement.changed", label: "Vacancy updated" }, { key: "recruiter.email", label: "Recruiter email" }],
});
const NONE = { type: "", channel: "", offset: 0 };

function answer(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("DeliveryExceptionsPanel", () => {
  it("shows the type, recipient, channel, error and attempts", () => {
    render(<DeliveryExceptionsPanel page={page([ROW])} filters={NONE} />);
    expect(screen.getByRole("heading", { name: "Asha Rao" })).toBeTruthy();
    expect(screen.getByText("Vacancy updated · WhatsApp")).toBeTruthy();
    expect(screen.getByText("provider down")).toBeTruthy();
    expect(screen.getByText(/Attempts: 4/)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Failed deliveries (1)" })).toBeTruthy();
  });

  it("explains a recruiter email, which records no error text", () => {
    render(<DeliveryExceptionsPanel page={page([{ ...ROW, source: "email", channel: "email", error: null }])} filters={NONE} />);
    expect(screen.getByText("The email could not be sent.")).toBeTruthy();
  });

  it("retries: the row leaves the list and the count falls", async () => {
    const fetchMock = answer(200, { id: "d1", source: "delivery", status: "queued" });
    render(<DeliveryExceptionsPanel page={page([ROW])} filters={NONE} />);
    fireEvent.click(screen.getByRole("button", { name: "Retry Vacancy updated for Asha Rao" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Retry queued for Asha Rao"));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String((fetchMock.mock.calls as unknown[][])[0][0])).toBe("/api/v1/recruiter/notification-exceptions/delivery/d1/retry");
    expect(screen.queryByRole("heading", { name: "Asha Rao" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Failed deliveries (0)" })).toBeTruthy();
  });

  it("treats a 409 as already handled: the row leaves and says why", async () => {
    answer(409, { detail: "This notification is no longer failed" });
    render(<DeliveryExceptionsPanel page={page([ROW])} filters={NONE} />);
    fireEvent.click(screen.getByRole("button", { name: /Retry/ }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("no longer failed"));
    expect(screen.queryByRole("heading", { name: "Asha Rao" })).toBeNull();
  });

  it("keeps the row and shows the error when the retry fails", async () => {
    answer(500, { detail: "Server error" });
    render(<DeliveryExceptionsPanel page={page([ROW])} filters={NONE} />);
    fireEvent.click(screen.getByRole("button", { name: /Retry/ }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.getByRole("heading", { name: "Asha Rao" })).toBeTruthy();
    expect((screen.getByRole("button", { name: /Retry/ }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("has an empty state, and a different one under filters with a way back", () => {
    render(<DeliveryExceptionsPanel page={page([])} filters={NONE} />);
    expect(screen.getByText(/No failed deliveries\. Everything sent/)).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Clear filters" })).toBeNull();
    cleanup();
    render(<DeliveryExceptionsPanel page={page([])} filters={{ ...NONE, channel: "sms" }} />);
    expect(screen.getByText("No failed deliveries match these filters.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Clear filters" }).getAttribute("href")).toBe("/recruiter/notification-exceptions");
  });

  it("pages, keeping the filters", () => {
    render(<DeliveryExceptionsPanel page={{ ...page([ROW], 120), offset: 50 }} filters={{ ...NONE, channel: "sms", offset: 50 }} />);
    expect(screen.getByRole("link", { name: "Previous page" }).getAttribute("href")).toBe("/recruiter/notification-exceptions?channel=sms");
    expect(screen.getByRole("link", { name: "Next page" }).getAttribute("href")).toBe("/recruiter/notification-exceptions?channel=sms&offset=100");
  });

  it("filters with a plain GET form holding the current values", () => {
    render(<DeliveryExceptionsPanel page={page([ROW])} filters={{ ...NONE, type: "recruiter.email", channel: "email" }} />);
    expect((screen.getByLabelText("Type") as HTMLSelectElement).value).toBe("recruiter.email");
    expect((screen.getByLabelText("Channel") as HTMLSelectElement).value).toBe("email");
  });
});

describe("notificationExceptions helpers", () => {
  it("reads the query safely", () => {
    expect(parseFilters({ type: "it.job.new_match", channel: "sms", offset: "50" })).toEqual({ type: "it.job.new_match", channel: "sms", offset: 50 });
    expect(parseFilters({ channel: "pigeon", offset: "-1" })).toEqual({ type: "", channel: "", offset: 0 });
    expect(parseFilters({ channel: ["sms", "email"] })).toEqual({ type: "", channel: "", offset: 0 });
  });

  it("builds the URLs", () => {
    expect(listUrl(NONE)).toBe("/api/v1/recruiter/notification-exceptions?limit=50");
    expect(listUrl({ type: "a b", channel: "", offset: 50 })).toBe("/api/v1/recruiter/notification-exceptions?type=a+b&offset=50&limit=50");
    expect(pageHref(NONE)).toBe("/recruiter/notification-exceptions");
    expect(retryUrl({ source: "email", id: "m/1" })).toBe("/api/v1/recruiter/notification-exceptions/email/m%2F1/retry");
  });
});
