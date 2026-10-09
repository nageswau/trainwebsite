import { beforeEach, describe, expect, it, vi } from "vitest";

import BdmStageHistory from "@/components/BdmStageHistory";
import MeetingTable from "@/components/MeetingTable";
import PartnershipTasksPanel from "@/components/PartnershipTasksPanel";
import UniversityFollowUp from "@/components/UniversityFollowUp";
import UniversityDocuments from "@/components/UniversityDocuments";
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
  permissions: { can_edit: true, can_assign: false, can_publish: false, can_deactivate: false, can_edit_contacts: false, can_manage_documents: true, can_move_stage: true, can_reopen: false },
  pipeline: { stage: "interested", stage_label: "Interested", column: "interested", column_label: "Interested", changed_at: "2026-10-08T10:00:00Z", lost: null, stages: [] },
  follow_up: { // upc-020 TK14/TK15
    next_action: { id: "t1", title: "Follow-up call", due_on: "2026-09-18", priority: "high", band: "upcoming", assignee: { id: "p1", full_name: "Rahul", active: true } },
    last_action: { title: "Proposal sent", at: "2026-09-10T10:00:00Z" },
  },
};
const history = { items: [], total: 0, limit: 20, offset: 0 };
const meeting = { id: "m1", code: "UMT-000001", meeting_type: "introduction", starts_at: "2030-01-10T04:30:00Z", mode: "offline", status: "scheduled",
  university: { id: ID, name: "ABC" }, responsible: { id: "p1", full_name: "Rahul", active: true }, contact: null, warnings: [] };
const meetings = { items: [meeting], total: 7, limit: 5, offset: 0, counts: { upcoming: 1, awaiting_outcome: 0, completed: 6, cancelled: 0 } };
const documents = { items: [{ id: "d1" }], total: 1, limit: 200, offset: 0 };

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
      if (p.includes("/partnership/meetings")) return meetings as never; // upc-009
      if (p.includes("/documents")) return documents as never; // upc-026
      return { university } as never;
    });
    const tree = elements(await UniversityPage({ params: Promise.resolve({ id: ID }) }));
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/partnership/universities/${ID}/stage-history?limit=20&offset=0`);
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/partnership/visits?university_id=${ID}&limit=5`); // upc-010 Visits section
    expect(tree.find((el) => el.type === UniversityStagePanel)!.props.university).toEqual(university);
    const panelEl = tree.find((el) => el.type === PartnershipTasksPanel)!;
    expect(panelEl.key).toContain(university.pipeline.changed_at); // QA-01: a stage move's auto-task shows without a reload
    const panel = panelEl.props; // upc-020: the university's open follow-ups and tasks
    expect(panel).toMatchObject({ role: "partnership_manager", university: { id: ID, name: "ABC" }, canAdd: false });
    expect(tree.find((el) => el.type === UniversityFollowUp)!.props.followUp).toEqual(university.follow_up);
    const hist = tree.find((el) => el.type === BdmStageHistory)!.props;
    expect(hist).toMatchObject({ orgId: ID, initial: history, version: 0, url: `/api/v1/partnership/universities/${ID}/stage-history` });
    // upc-026: the Documents section, read beside the university
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/partnership/universities/${ID}/documents`);
    expect(tree.find((el) => el.type === UniversityDocuments)!.props).toEqual({ universityId: ID, documents: documents.items, canManage: true });
    // upc-009: the Meetings section, every view (scheduled first) for the meeting readers
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/partnership/meetings?university_id=${ID}&limit=5`);
    expect(tree.find((el) => el.type === MeetingTable)!.props).toMatchObject({ items: [meeting], total: 7, showUniversity: false });
    expect(tree.some((el) => el.props?.href === `/partnership/meetings?university_id=${ID}`)).toBe(true); // "All 7 meetings"
  });

  it("a failed history read still shows the page, with Try again in the section", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => {
      if (p === "/api/v1/auth/me") return { role: "partnership_manager", full_name: "Rahul" } as never;
      if (p.includes("/stage-history")) throw new Error("down");
      if (p.includes("/contacts")) return { items: [], total: 0, limit: 50, offset: 0 } as never;
      if (p.includes("/partnership/visits")) return { items: [], total: 0, limit: 5, offset: 0 } as never;
      if (p.includes("/partnership/meetings")) return meetings as never;
      if (p.includes("/documents")) return documents as never;
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
    if (p.includes("/partnership/meetings")) return meetings as never;
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
    expect(tree.find((el) => el.type === MeetingTable)).toBeUndefined(); // upc-009 MG14: meetings are not read for overseas_admin
    expect(serverApi).not.toHaveBeenCalledWith(expect.stringContaining("/partnership/meetings"));
  });
});
