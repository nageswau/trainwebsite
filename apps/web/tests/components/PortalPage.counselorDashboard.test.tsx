import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import CounselorDashboardPanel from "@/components/CounselorDashboardPanel";
import CounselorQuickSearch from "@/components/CounselorQuickSearch";
import PortalPage from "@/components/PortalPage";
import PortalSection from "@/components/PortalSection";
import { serverApi } from "@/lib/api";
import { elements } from "@/tests/helpers/elementTree";

// ccrm-032 (DEC-SCOPE-277 D8/D9): the overseas counselor's dashboard leads with the quick search, then the action sections (streamed in
// on their own endpoint); the payload's tiles and table stay below. Nobody else's dashboard gets the sections.
vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("notFound"); } }));
vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
const api = vi.mocked(serverApi);
const payload = { title: "Counselor Dashboard", subtitle: "", columns: [], rows: [], metrics: [{ label: "Applications", value: 2 }] };

async function page(division: "it" | "overseas", role: string) {
  api.mockImplementation((path: string) => Promise.resolve(path === "/api/v1/auth/me" ? { id: "u1", role, full_name: "C", email: "c@x" } : payload));
  const tree = elements(await PortalPage({ division, role, section: "dashboard" }));
  const section = tree.find((el) => el.type === PortalSection);
  return { section, lead: elements(section?.props.lead as ReactNode) };
}

describe("PortalPage counselor dashboard", () => {
  it("puts the quick search and the action sections above the overseas counselor's tiles", async () => {
    const { section, lead } = await page("overseas", "counselor");
    expect(lead.some((el) => el.type === CounselorQuickSearch)).toBe(true);
    expect(lead.some((el) => el.type === CounselorDashboardPanel)).toBe(true);
    expect((section?.props.data as typeof payload).metrics).toHaveLength(1); // D8: the ccrm-001 tiles stay
  });

  it("leaves the overseas admin's dashboard without the sections", async () => {
    const { lead } = await page("overseas", "admin");
    expect(lead.some((el) => el.type === CounselorDashboardPanel)).toBe(false);
  });
});
