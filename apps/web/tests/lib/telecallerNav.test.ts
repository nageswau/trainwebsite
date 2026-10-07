import { afterEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ serverApi: vi.fn() }));
vi.mock("@/lib/api", () => ({ serverApi: api.serverApi }));

import { TELECALLER_NAV, TELECALLER_NOTIFICATIONS_HREF } from "@/lib/navigation";
import { telecallerNav } from "@/lib/telecallerNav";

afterEach(() => api.serverApi.mockReset());

// tel-020: the telecaller sidebar carries Notifications with the unread count (the bdm-010 badge pattern).
describe("telecallerNav", () => {
  it("lists Notifications and badges the unread count", async () => {
    expect(TELECALLER_NAV.map((i) => i.href)).toContain(TELECALLER_NOTIFICATIONS_HREF);
    api.serverApi.mockResolvedValue({ unread: 3 });
    const nav = await telecallerNav();
    expect(nav.find((i) => i.href === TELECALLER_NOTIFICATIONS_HREF)?.badge).toBe(3);
    expect(api.serverApi).toHaveBeenCalledWith("/api/v1/workflows/notifications/unread-count");
  });

  it("renders without a badge when the count cannot be read", async () => {
    api.serverApi.mockRejectedValue(new Error("down"));
    const nav = await telecallerNav();
    expect(nav.find((i) => i.href === TELECALLER_NOTIFICATIONS_HREF)?.badge).toBeUndefined();
  });
});
