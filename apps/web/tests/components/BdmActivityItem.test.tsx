import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmActivityItem from "@/components/BdmActivityItem";
import type { Activity } from "@/lib/bdmActivities";

const res = (body: unknown, status = 200) => new Response(body === null ? null : JSON.stringify(body), { status });
const item = (over: Partial<Activity> = {}): Activity => ({
  id: "a1", organization: { id: "o1", code: "ORG-000001", name: "St Mary", org_type: "college" }, bdm: { id: "b1", full_name: "Asha" },
  contact_id: null, contact_name: "Dr Rao", contact_removed: true, channel: "whatsapp", direction: "inbound", occurred_at: "2026-10-03T05:00:00Z",
  note: "Sent brochure", created_at: "2026-10-03T05:00:00Z", updated_at: "2026-10-03T05:00:00Z", permissions: { can_change: true }, ...over,
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmActivityItem (bdm-009 §6.3)", () => {
  it("shows channel, direction, removed contact, logger and note; org link only when asked", () => {
    const { rerender } = render(<BdmActivityItem activity={item()} onChanged={vi.fn()} onDeleted={vi.fn()} />);
    expect(screen.getByText("WhatsApp · Incoming")).toBeInTheDocument();
    expect(screen.getByText(/Dr Rao \(removed\)/)).toBeInTheDocument();
    expect(screen.getByText(/Asha/)).toBeInTheDocument();
    expect(screen.getByText("Sent brochure")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "St Mary" })).toBeNull();
    rerender(<BdmActivityItem activity={item()} showOrganization orgBasePath="/bdm/organizations" onChanged={vi.fn()} onDeleted={vi.fn()} />);
    expect(screen.getByRole("link", { name: "St Mary" })).toHaveAttribute("href", "/bdm/organizations/o1");
  });

  it("shows markup in a note as text (AC13, §12.3 S5)", () => {
    const { container } = render(<BdmActivityItem activity={item({ note: "<script>alert(1)</script><b>x</b>" })} onChanged={vi.fn()} onDeleted={vi.fn()} />);
    expect(screen.getByText("<script>alert(1)</script><b>x</b>")).toBeInTheDocument();
    expect(container.querySelector("script, b")).toBeNull();
  });

  it("hides Edit and Delete without can_change", () => {
    render(<BdmActivityItem activity={item({ permissions: { can_change: false } })} onChanged={vi.fn()} onDeleted={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /Edit|Delete/ })).toBeNull();
  });

  it("deletes after a confirm", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(null, 204))));
    const onDeleted = vi.fn();
    render(<BdmActivityItem activity={item()} onChanged={vi.fn()} onDeleted={onDeleted} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("a1"));
  });

  it("a 409 makes the item read-only with the reason; a 404 removes it", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Only today's activities can be changed" }, 409))));
    const onChanged = vi.fn();
    render(<BdmActivityItem activity={item()} onChanged={onChanged} onDeleted={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only today's activities can be changed");
    expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ permissions: { can_change: false } }));
    cleanup();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Activity not found" }, 404))));
    const onDeleted = vi.fn();
    render(<BdmActivityItem activity={item()} onChanged={vi.fn()} onDeleted={onDeleted} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("a1"));
  });
});
