import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmMouHistory from "@/components/BdmMouHistory";
import BdmMouPrevious from "@/components/BdmMouPrevious";
import { mou, res } from "./BdmMouFixtures";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const actor = { id: "u1", full_name: "Asha BDM" };
const event = (over: Record<string, unknown>) => ({ id: String(Math.random()), from_status: null, from_label: null, changed: [], actor, created_at: "2026-10-06T05:00:00Z", ...over });
const page = (items: unknown[], total = items.length) => ({ items, total, limit: 20, offset: 0 });
const open = (name: string) => fireEvent.click(screen.getByText(name));

describe("BdmMouHistory (bdm-005 AC1)", () => {
  it("loads when opened and names each change with its actor", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res(page([
      event({ kind: "updated", from_status: "signed", from_label: "Signed", to_status: "signed", to_label: "Signed", changed: ["notes", "valid_until"] }),
      event({ kind: "status", from_status: "prospect", from_label: "Prospect", to_status: "signed", to_label: "Signed", changed: ["status"] }),
      event({ kind: "created", to_status: "prospect", to_label: "Prospect" }),
    ])));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmMouHistory mou={mou("signed")} />);
    expect(fetchMock).not.toHaveBeenCalled();
    open("MoU history");
    const list = await screen.findByRole("list", { name: "MoU history" });
    expect(within(list).getAllByRole("listitem").map((li) => li.querySelector(".jtl-title")?.textContent)).toEqual([
      "Updated: Notes, Valid until", "Prospect → Signed", "Started at Prospect",
    ]);
    expect(within(list).getAllByText("By Asha BDM")).toHaveLength(3);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/bdm/mous/m1/history?limit=20&offset=0");
  });

  it("shows the automatic Expired line first, with no actor", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([event({ kind: "created", to_status: "active", to_label: "Active" })]))));
    render(<BdmMouHistory mou={mou("expired", { expired_on: "2026-10-06" })} />);
    open("MoU history");
    const list = await screen.findByRole("list", { name: "MoU history" });
    const first = within(list).getAllByRole("listitem")[0];
    expect(first).toHaveTextContent("Expired (automatic)");
    expect(first).not.toHaveTextContent("By ");
  });

  it("explains a failed load and tries again, and pages with Show more", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(res({ detail: "x" }, 500))
      .mockResolvedValueOnce(res(page([event({ kind: "created", to_status: "prospect", to_label: "Prospect" })], 2)))
      .mockResolvedValueOnce(res({ ...page([event({ kind: "document", to_status: "prospect", to_label: "Prospect", changed: ["document"] })], 2), offset: 1 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmMouHistory mou={mou()} />);
    open("MoU history");
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    fireEvent.click(await screen.findByRole("button", { name: "Show more" }));
    await waitFor(() => expect(screen.getByText("Document uploaded")).toBeInTheDocument());
    expect(fetchMock.mock.calls[2][0]).toBe("/api/v1/bdm/mous/m1/history?limit=20&offset=1");
  });
});

describe("BdmMouPrevious (bdm-005 M6)", () => {
  it("lists renewed MoUs on open, each with its own scoped download", async () => {
    const old = { ...mou("expired", { id: "m0", reference: "MOU-OLD", has_document: true, valid_until: "2026-09-30", is_current: false }) };
    const fetchMock = vi.fn().mockResolvedValue(res(page([old])));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmMouPrevious orgId="o1" />);
    open("Previous MoUs");
    expect(await screen.findByText(/MOU-OLD/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download MOU-OLD" })).toHaveAttribute("href", "/api/v1/bdm/mous/m0/document");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/bdm/mous?organization=o1&current=false&limit=50&offset=0");
  });

  it("says when there are none", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([]))));
    render(<BdmMouPrevious orgId="o1" />);
    open("Previous MoUs");
    expect(await screen.findByText("No previous MoUs.")).toBeInTheDocument();
  });
});
