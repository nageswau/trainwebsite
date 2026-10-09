import Link from "next/link";
import { Suspense } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import PortalShell from "@/components/PortalShell";
import RecruiterCandidateDetail from "@/components/RecruiterCandidateDetail";
import RecruiterCandidateForm from "@/components/RecruiterCandidateForm";
import RecruiterCandidateList from "@/components/RecruiterCandidateList";
import RecruiterFindCandidates from "@/components/RecruiterFindCandidates";
import RecruiterTalentPool from "@/components/RecruiterTalentPool";
import RecruiterTalentPools from "@/components/RecruiterTalentPools";
import { ApiError, serverApi } from "@/lib/api";
import { PORTAL_NAV, RECRUITER_MANAGER_NAV, RECRUITER_NAV, SUPER_ADMIN_NAV, type NavItem } from "@/lib/navigation";
import { PLACEMENT_MANAGER_LABEL, RECRUITER_ROLE_LABEL } from "@/lib/recruiter";
import { CANDIDATES_PATH, candidateUrl, type CandidateDetail } from "@/lib/recruiterCandidates";
import { POOLS_PATH } from "@/lib/recruiterPools";
import type { User } from "@/lib/types";

// rec-009 (spec §6): the candidate master's three pages -- list, add, detail -- shared by recruiters, placement managers, super_admin
// and (read only) hr_team, each in their own navigation. The API is the gate; the role check only spares other roles a screen that can
// only fail. Signed out, the middleware sends /recruiter/* to /it/login (rec-001 Q-29).
const SHELLS: Record<string, { nav: NavItem[]; label: string; writes: boolean }> = {
  placement_team: { nav: RECRUITER_NAV, label: RECRUITER_ROLE_LABEL, writes: true },
  placement_manager: { nav: RECRUITER_MANAGER_NAV, label: PLACEMENT_MANAGER_LABEL, writes: true },
  super_admin: { nav: SUPER_ADMIN_NAV, label: "Super Administrator", writes: true },
  hr_team: { nav: PORTAL_NAV["it/hr"], label: "HR Team", writes: false },
};
type Shell = { nav: NavItem[]; label: string; writes: boolean; userName: string };

async function shell(): Promise<Shell | React.ReactElement> {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/it/login");
  }
  const found = SHELLS[user.role];
  return found ? { ...found, userName: user.full_name } : accessDenied(user, "Your role cannot view candidates");
}

function Frame({ s, children }: { s: Shell; children: React.ReactNode }) {
  return (
    <PortalShell nav={s.nav} roleLabel={s.label} userName={s.userName}>
      <div className="portal-content">{children}</div>
    </PortalShell>
  );
}

const Back = () => <p style={{ margin: "0 0 12px" }}><Link href={CANDIDATES_PATH}>← Back to candidates</Link></p>;

export async function CandidateListPage() {
  const s = await shell();
  if (!("nav" in s)) return s;
  return (
    <Frame s={s}>
      <div className="portal-title">
        <div>
          <div className="eyebrow">Candidate master</div>
          <h2>Candidates</h2>
          <p className="muted">One central list of every candidate, with where each came from.{s.writes ? "" : " You can view candidates and download resumes."}</p>
        </div>
        {s.writes && <Link className="btn" href={`${CANDIDATES_PATH}/new`}>+ Add candidate</Link>}
      </div>
      <Suspense fallback={<p className="muted" role="status">Loading candidates…</p>}>
        <RecruiterCandidateList sourceFilter={s.writes} />
      </Suspense>
    </Frame>
  );
}

/** rec-013 (DEC-SCOPE-151): Find Candidates, in the same shell and for the same roles as the list. */
export async function FindCandidatesPage() {
  const s = await shell();
  if (!("nav" in s)) return s;
  return (
    <Frame s={s}>
      <div className="portal-title">
        <div>
          <div className="eyebrow">Candidate pool</div>
          <h2>Find Candidates</h2>
          <p className="muted">Search every candidate by skill — other names for a skill and related skills count too — or by words in their resume, then narrow by experience, location and availability.</p>
        </div>
      </div>
      <Suspense fallback={<p className="muted" role="status">Loading search…</p>}>
        <RecruiterFindCandidates writes={s.writes} sourceFilter={s.writes} />
      </Suspense>
    </Frame>
  );
}

// rec-015 (DEC-SCOPE-158): talent pools -- the same readers as Find Candidates; the API tells the page who may create and edit (P6).
export async function TalentPoolsPage() {
  const s = await shell();
  if (!("nav" in s)) return s;
  return (
    <Frame s={s}>
      <div className="portal-title">
        <div>
          <div className="eyebrow">Candidate pool</div>
          <h2>Talent Pools</h2>
          <p className="muted">Ready-made groups of candidates by skill and experience. Candidates join a pool automatically as soon as they match its rule.</p>
        </div>
      </div>
      <RecruiterTalentPools />
    </Frame>
  );
}

export async function TalentPoolPage({ id }: { id: string }) {
  const s = await shell();
  if (!("nav" in s)) return s;
  return (
    <Frame s={s}>
      <p style={{ margin: "0 0 12px" }}><Link href={POOLS_PATH}>← Back to talent pools</Link></p>
      <RecruiterTalentPool poolId={id} />
    </Frame>
  );
}

export async function NewCandidatePage() {
  const s = await shell();
  if (!("nav" in s)) return s;
  if (!s.writes) return <Frame s={s}><Back /><div className="action-card"><h2>Read only</h2><p>Your role can view candidates but not add them.</p></div></Frame>;
  return (
    <Frame s={s}>
      <Back />
      <div className="portal-title">
        <div>
          <div className="eyebrow">Candidate master</div>
          <h2>Add candidate</h2>
          <p className="muted">We check the mobile number and email against every candidate first, so a person is never entered twice.</p>
        </div>
      </div>
      <RecruiterCandidateForm />
    </Frame>
  );
}

/** A 404 (unknown, or outside the pool) or a malformed id (422) is a plain "not found" -- it never says which. */
export async function CandidateDetailPage({ id }: { id: string }) {
  const s = await shell();
  if (!("nav" in s)) return s;
  let candidate: CandidateDetail | null = null;
  try {
    candidate = await serverApi<CandidateDetail>(candidateUrl(id));
  } catch (e) {
    if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) return accessUnavailable(e, "/it/login");
  }
  return (
    <Frame s={s}>
      <Back />
      {candidate ? <RecruiterCandidateDetail initial={candidate} /> : (
        <div className="action-card">
          <h2>Candidate not found</h2>
          <p>This candidate does not exist.</p>
        </div>
      )}
    </Frame>
  );
}
