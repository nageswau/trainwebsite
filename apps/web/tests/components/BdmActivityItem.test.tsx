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
    const { rerender } = render(<BdmActivityItem activity={item()} onChanged={vi.fn()} onDeleted={vi.fn()} onLocked={vi.fn()} />);
    expect(screen.getByText("WhatsApp · Incoming")).toBeInTheDocument();
    expect(screen.getByText(/Dr Rao \(removed\)/)).toBeInTheDocument();
    expect(screen.getByText(/Asha/)).toBeInTheDocument();
    expect(screen.getByText("Sent brochure")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "St Mary" })).toBeNull();
    rerender(<BdmActivityItem activity={item()} showOrganization orgBasePath="/bdm/organizations" onChanged={vi.fn()} onDeleted={vi.fn()} onLocked={vi.fn()} />);
    expect(screen.getByRole("link", { name: "St Mary" })).toHaveAttribute("href", "/bdm/organizations/o1");
  });

  it("shows markup in a note as text (AC13, §12.3 S5)", () => {
    const { container } = render(<BdmActivityItem activity={item({ note: "<script>alert(1)</script><b>x</b>" })} onChanged={vi.fn()} onDeleted={vi.fn()} onLocked={vi.fn()} />);
    expect(screen.getByText("<script>alert(1)</script><b>x</b>")).toBeInTheDocument();
    expect(container.querySelector("script, b")).toBeNull();
  });

  it("hides Edit and Delete without can_change", () => {
    render(<BdmActivityItem activity={item({ permissions: { can_change: false } })} onChanged={vi.fn()} onDeleted={vi.fn()} onLocked={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /Edit|Delete/ })).toBeNull();
  });

  it("deletes after a confirm", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(null, 204))));
    const onDeleted = vi.fn();
    render(<BdmActivityItem activity={item()} onChanged={vi.fn()} onDeleted={onDeleted} onLocked={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("a1"));
  });

  const del = () => {
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
  };
  const props = () => ({ onChanged: vi.fn(), onDeleted: vi.fn(), onLocked: vi.fn() });

  it("a delete 409 shows the reason and locks the item without calling onChanged; a 404 removes it", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Only today's activities can be changed" }, 409))));
    const p = props();
    render(<BdmActivityItem activity={item()} {...p} />);
    del();
    expect(await screen.findByRole("alert")).toHaveTextContent("Only today's activities can be changed");
    expect(p.onLocked).toHaveBeenCalledWith("a1");
    expect(p.onChanged).not.toHaveBeenCalled();
    cleanup();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Activity not found" }, 404))));
    const q = props();
    render(<BdmActivityItem activity={item()} {...q} />);
    del();
    await waitFor(() => expect(q.onDeleted).toHaveBeenCalledWith("a1"));
  });

  const edit = () => {
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: "changed" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  };

  it.each([403, 409])("an edit %i closes the form, shows the reason and makes the item read-only", async (status) => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Only today's activities can be changed" }, status))));
    const p = props();
    const { rerender } = render(<BdmActivityItem activity={item()} {...p} />);
    edit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Only today's activities can be changed");
    expect(screen.queryByRole("form", { name: "Edit activity" })).toBeNull();
    expect(p.onLocked).toHaveBeenCalledWith("a1");
    expect(p.onChanged).not.toHaveBeenCalled();
    rerender(<BdmActivityItem activity={item({ permissions: { can_change: false } })} {...p} />);
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.getByRole("alert")).toHaveTextContent("Only today's activities can be changed");
  });

  it("focuses the refusal alert after a refused delete or edit (QA9B-03)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Only today's activities can be changed" }, 409))));
    render(<BdmActivityItem activity={item()} {...props()} />);
    del();
    await waitFor(() => expect(screen.getByRole("alert")).toHaveFocus());
    cleanup();
    render(<BdmActivityItem activity={item()} {...props()} />);
    edit();
    await waitFor(() => expect(screen.getByRole("alert")).toHaveFocus());
  });

  it("an edit 404 removes the item", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Activity not found" }, 404))));
    const p = props();
    render(<BdmActivityItem activity={item()} {...p} />);
    edit();
    await waitFor(() => expect(p.onDeleted).toHaveBeenCalledWith("a1"));
    expect(p.onLocked).not.toHaveBeenCalled();
  });
});
