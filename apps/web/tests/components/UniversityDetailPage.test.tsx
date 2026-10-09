import { beforeEach, describe, expect, it, vi } from "vitest";

import BdmStageHistory from "@/components/BdmStageHistory";
import UniversityCalls from "@/components/UniversityCalls";
import UniversityMessages from "@/components/UniversityMessages";
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

describe("upc-012 university detail page", () => {
  const contact = { id: "K1", name: "Priya Raman", phone: null, whatsapp: "+91 98450 00000", email: "p@abc.ac.uk", whatsapp_to: "919845000000" };
  const serve = (role: string, canEditContacts: boolean) => vi.mocked(serverApi).mockImplementation(async (p: string) => {
    if (p === "/api/v1/auth/me") return { role, full_name: "Rahul" } as never;
    if (p.includes("/stage-history")) return history as never;
    if (p.includes("/contacts")) return { items: [contact], total: 1, limit: 50, offset: 0 } as never;
    if (p.includes("/partnership/visits")) return { items: [], total: 0, limit: 5, offset: 0 } as never;
    return { university: { ...university, permissions: { ...university.permissions, can_edit_contacts: canEditContacts } } } as never;
  });

  it("shows Calls and Messages to the partnership roles, with the contacts as recipients and the write right (UC3)", async () => {
    serve("partnership_manager", true);
    const tree = elements(await UniversityPage({ params: Promise.resolve({ id: ID }) }));
    const calls = tree.find((el) => el.type === UniversityCalls)!.props;
    expect(calls).toMatchObject({ universityId: ID, canWrite: true, contacts: [{ id: "K1", name: "Priya Raman", phone: "+91 98450 00000" }] });
    expect(tree.find((el) => el.type === UniversityMessages)!.props).toMatchObject({ universityId: ID, canWrite: true, contacts: [contact] });
  });

  it("hides them from overseas_admin, who reads the master only", async () => {
    serve("overseas_admin", false);
    const tree = elements(await UniversityPage({ params: Promise.resolve({ id: ID }) }));
    expect(tree.find((el) => el.type === UniversityCalls)).toBeUndefined();
    expect(tree.find((el) => el.type === UniversityMessages)).toBeUndefined();
  });
});
