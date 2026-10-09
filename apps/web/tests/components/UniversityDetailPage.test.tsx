import { beforeEach, describe, expect, it, vi } from "vitest";

import BdmStageHistory from "@/components/BdmStageHistory";
import PartnershipTasksPanel from "@/components/PartnershipTasksPanel";
import UniversityFollowUp from "@/components/UniversityFollowUp";
import UniversityStagePanel from "@/components/UniversityStagePanel";
import { serverApi } from "@/lib/api";
import UniversityPage from "@/app/partnership/universities/[id]/page";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const ID = "3f2b6a8e-1c4d-4e5f-8a9b-0c1d2e3f4a5b";
const university = {
  id: ID, university_code: "UNV-000001", name: "ABC", city: "London", country: { name: "United Kingdom", region: "UK" }, active: true,
  catalogue_visible: false, course_levels: [], popular_programs: [], rankings: [], application_count: 0, overview: "",
  relationship_strength: null, linked_bdm_organizations: [], // upc-006 / upc-004 fields
  permissions: { can_edit: true, can_assign: false, can_publish: false, can_deactivate: false, can_edit_contacts: false, can_move_stage: true, can_reopen: false },
  pipeline: { stage: "interested", stage_label: "Interested", column: "interested", column_label: "Interested", changed_at: "2026-10-08T10:00:00Z", lost: null, stages: [] },
  follow_up: { // upc-020 TK14/TK15
    next_action: { id: "t1", title: "Follow-up call", due_on: "2026-09-18", priority: "high", band: "upcoming", assignee: { id: "p1", full_name: "Rahul", active: true } },
    last_action: { title: "Proposal sent", at: "2026-09-10T10:00:00Z" },
  },
};
const history = { items: [], total: 0, limit: 20, offset: 0 };

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});

describe("upc-007 university detail page", () => {
  it("adds the stage panel and the stage history (first page read with the university)", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => {
      if (p === "/api/v1/auth/me") return { role: "partnership_manager", full_name: "Rahul" } as never;
      if (p.includes("/stage-history")) return history as never;
      if (p.includes("/contacts")) return { items: [], total: 0, limit: 50, offset: 0 } as never; // upc-006
      if (p.includes("/partnership/visits")) return { items: [], total: 0, limit: 5, offset: 0 } as never; // upc-010
      return { university } as never;
    });
    const tree = elements(await UniversityPage({ params: Promise.resolve({ id: ID }) }));
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/partnership/universities/${ID}/stage-history?limit=20&offset=0`);
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/partnership/visits?university_id=${ID}&limit=5`); // upc-010 Visits section
    expect(tree.find((el) => el.type === UniversityStagePanel)!.props.university).toEqual(university);
    const panel = tree.find((el) => el.type === PartnershipTasksPanel)!.props; // upc-020: the university's open follow-ups and tasks
    expect(panel).toMatchObject({ role: "partnership_manager", university: { id: ID, name: "ABC" }, canAdd: false });
    expect(tree.find((el) => el.type === UniversityFollowUp)!.props.followUp).toEqual(university.follow_up);
    const hist = tree.find((el) => el.type === BdmStageHistory)!.props;
    expect(hist).toMatchObject({ orgId: ID, initial: history, version: 0, url: `/api/v1/partnership/universities/${ID}/stage-history` });
  });

  it("a failed history read still shows the page, with Try again in the section", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => {
      if (p === "/api/v1/auth/me") return { role: "partnership_manager", full_name: "Rahul" } as never;
      if (p.includes("/stage-history")) throw new Error("down");
      if (p.includes("/contacts")) return { items: [], total: 0, limit: 50, offset: 0 } as never;
      if (p.includes("/partnership/visits")) return { items: [], total: 0, limit: 5, offset: 0 } as never;
      return { university } as never;
    });
    const tree = elements(await UniversityPage({ params: Promise.resolve({ id: ID }) }));
    expect(tree.find((el) => el.type === BdmStageHistory)!.props.initial).toBeNull();
  });
});
