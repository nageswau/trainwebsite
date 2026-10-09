import { beforeEach, describe, expect, it, vi } from "vitest";

import BdmStageHistory from "@/components/BdmStageHistory";
import MeetingTable from "@/components/MeetingTable";
import PartnershipTasksPanel from "@/components/PartnershipTasksPanel";
import UniversityAgreements from "@/components/UniversityAgreements";
import UniversityFollowUp from "@/components/UniversityFollowUp";
import UniversityDocuments from "@/components/UniversityDocuments";
import UniversityCalls from "@/components/UniversityCalls";
import UniversityMessages from "@/components/UniversityMessages";
import UniversityStagePanel from "@/components/UniversityStagePanel";
import UniversityTimeline from "@/components/UniversityTimeline";
import { serverApi } from "@/lib/api";
import UniversityPage from "@/app/partnership/universities/[id]/page";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const ID = "3f2b6a8e-1c4d-4e5f-8a9b-0c1d2e3f4a5b";
const university = {
  id: ID, university_code: "UNV-000001", name: "ABC", city: "London", country: { name: "United Kingdom", region: "UK" }, active: true,
  catalogue_visible: false, course_levels: [], popular_programs: [], rankings: [], application_count: 0, overview: "",
  relationship_strength: null, linked_bdm_organizations: [], // upc-006 / upc-004 fields
  permissions: { can_edit: true, can_assign: false, can_publish: false, can_deactivate: false, can_edit_contacts: false, can_manage_documents: true, can_move_stage: true, can_reopen: false, can_manage_agreements: true, can_approve_agreements: false, can_edit_timeline: true },
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
const milestones = { items: [], today: "2026-10-09", can_edit: true }; // upc-008
const documents = { items: [{ id: "d1" }], total: 1, limit: 200, offset: 0 };
const agreements = { items: [{ id: "a1" }], total: 1, limit: 50, offset: 0 }; // upc-014
const options = { courses: [], documents: [] };

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});

describe("upc-007 university detail page", () => {
  it("adds the stage panel and the stage history (first page read with the university)", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => {
      if (p === "/api/v1/auth/me") return { role: "partnership_manager", full_name: "Rahul" } as never;
      if (p.includes("/stage-history")) return history as never;
      if (p.includes("/milestones")) return milestones as never; // upc-008
      if (p.includes("/contacts")) return { items: [], total: 0, limit: 50, offset: 0 } as never; // upc-006
      if (p.includes("/partnership/visits")) return { items: [], total: 0, limit: 5, offset: 0 } as never; // upc-010
      if (p.includes("/partnership/meetings")) return meetings as never; // upc-009
      if (p.includes("/documents")) return documents as never; // upc-026
      if (p.includes("/agreement-options")) return options as never; // upc-014
      if (p.includes("/agreements")) return agreements as never;
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
    // upc-014: the Agreements section, with the form's options for a manager who may write
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/partnership/universities/${ID}/agreements`);
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/partnership/universities/${ID}/agreement-options`);
    expect(tree.find((el) => el.type === UniversityAgreements)!.props).toEqual({ universityId: ID, agreements: agreements.items, options, canManage: true });
  });

  it("an overseas_admin never asks for agreements (upc-014 AG13)", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => {
      if (p === "/api/v1/auth/me") return { role: "overseas_admin", full_name: "Asha" } as never;
      if (p.includes("/stage-history")) return history as never;
      if (p.includes("/contacts")) return { items: [], total: 0, limit: 50, offset: 0 } as never;
      if (p.includes("/documents")) return documents as never;
      return { university: { ...university, permissions: { ...university.permissions, can_manage_agreements: false } } } as never;
    });
    const tree = elements(await UniversityPage({ params: Promise.resolve({ id: ID }) }));
    expect(vi.mocked(serverApi).mock.calls.some(([p]) => String(p).includes("agreement"))).toBe(false);
    expect(tree.find((el) => el.type === UniversityAgreements)).toBeUndefined();
  });

  it("a failed history read still shows the page, with Try again in the section", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => {
      if (p === "/api/v1/auth/me") return { role: "partnership_manager", full_name: "Rahul" } as never;
      if (p.includes("/stage-history")) throw new Error("down");
      if (p.includes("/contacts")) return { items: [], total: 0, limit: 50, offset: 0 } as never;
      if (p.includes("/partnership/visits")) return { items: [], total: 0, limit: 5, offset: 0 } as never;
      if (p.includes("/partnership/meetings")) return meetings as never;
      if (p.includes("/documents")) return documents as never;
      if (p.includes("/agreement-options")) return options as never;
      if (p.includes("/agreements")) return agreements as never;
      return { university } as never;
    });
    const tree = elements(await UniversityPage({ params: Promise.resolve({ id: ID }) }));
    expect(tree.find((el) => el.type === BdmStageHistory)!.props.initial).toBeNull();
  });
});

describe("upc-008 university detail page", () => {
  const expected = { target_partnership_date: "2026-11-15", expected_month: "2026-11", expected_quarter: "2026-Q4", expected_intake: null,
    expected_agreement_date: null, expected_recruitment_start: null };
  const serve = (milestonesRead: () => Promise<unknown>) => vi.mocked(serverApi).mockImplementation(async (p: string) => {
    if (p === "/api/v1/auth/me") return { role: "overseas_admin", full_name: "Asha" } as never;
    if (p.includes("/stage-history")) return history as never;
    if (p.includes("/milestones")) return milestonesRead() as never;
    if (p.includes("/contacts")) return { items: [], total: 0, limit: 50, offset: 0 } as never;
    if (p.includes("/documents")) return documents as never;
    return { university: { ...university, expected, permissions: { ...university.permissions, can_edit_timeline: false } } } as never;
  });

  it("adds the Partnership timeline for every reader, read with the university and remounted after a stage move", async () => {
    serve(async () => milestones);
    const tree = elements(await UniversityPage({ params: Promise.resolve({ id: ID }) }));
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/partnership/universities/${ID}/milestones`);
    const timeline = tree.find((el) => el.type === UniversityTimeline)!;
    expect(timeline.props).toEqual({ universityId: ID, expected, canEdit: false, initial: milestones });
    expect(timeline.key).toContain(university.pipeline.changed_at); // a move into Proposal Sent auto-completes Proposal (MS4)
  });

  it("a failed milestones read still shows the page, with Try again in the section", async () => {
    serve(async () => { throw new Error("down"); });
    const tree = elements(await UniversityPage({ params: Promise.resolve({ id: ID }) }));
    expect(tree.find((el) => el.type === UniversityTimeline)!.props.initial).toBeNull();
  });
});

describe("upc-012 university detail page", () => {
  const contact = { id: "K1", name: "Priya Raman", phone: null, whatsapp: "+91 98450 00000", email: "p@abc.ac.uk", whatsapp_to: "919845000000" };
  const serve = (role: string, canEditContacts: boolean) => vi.mocked(serverApi).mockImplementation(async (p: string) => {
    if (p === "/api/v1/auth/me") return { role, full_name: "Rahul" } as never;
    if (p.includes("/stage-history")) return history as never;
    if (p.includes("/milestones")) return milestones as never; // upc-008
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
