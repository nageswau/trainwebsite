import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import SchoolNotificationList, { type NotificationItem } from "@/components/SchoolNotificationList";

// itc-002 (DEC-SCOPE-336): typed notices can be filtered by type; a list with no typed notice looks exactly as before.
afterEach(cleanup);

const n = (id: string, over: Partial<NotificationItem> = {}): NotificationItem => ({ id, title: `Title ${id}`, body: `Body ${id}`, read: true, action_url: null, created_at: "2026-11-02T10:00:00Z", ...over });
const paid = (id: string) => n(id, { title: "Payment received", event_type: "it.fee.payment_received", entity_type: "payment", entity_id: `p${id}`, action_url: "/it/student/fees" });
const batch = (id: string) => n(id, { title: "Course or batch updated", event_type: "it.batch.changed", entity_type: "batch", entity_id: `b${id}` });

describe("SchoolNotificationList type filter (itc-002)", () => {
  it("shows no filter when no notice has a type", () => {
    render(<SchoolNotificationList notifications={[n("1"), n("2")]} emptyText="none" />);
    expect(screen.queryByLabelText("Type")).toBeNull();
  });

  it("offers All plus each type present, named by its title", () => {
    render(<SchoolNotificationList notifications={[paid("1"), batch("2"), paid("3"), n("4")]} emptyText="none" />);
    const select = screen.getByLabelText("Type") as HTMLSelectElement;
    expect([...select.options].map((o) => o.textContent)).toEqual(["All", "Course or batch updated", "Payment received"]);
    expect(select.value).toBe("");
    expect(screen.getAllByRole("listitem")).toHaveLength(4);
  });

  it("narrows the list to the chosen type and back to all", () => {
    render(<SchoolNotificationList notifications={[paid("1"), batch("2"), paid("3"), n("4")]} emptyText="none" />);
    const select = screen.getByLabelText("Type");
    fireEvent.change(select, { target: { value: "it.fee.payment_received" } });
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText(/Showing 2 of 4/)).toBeTruthy();
    fireEvent.change(select, { target: { value: "" } });
    expect(screen.getAllByRole("listitem")).toHaveLength(4);
  });

  it("deep-links a typed notice through its action_url", () => {
    render(<SchoolNotificationList notifications={[paid("1")]} emptyText="none" />);
    expect(screen.getByRole("link", { name: "Open: Payment received" }).getAttribute("href")).toBe("/it/student/fees");
  });
});
