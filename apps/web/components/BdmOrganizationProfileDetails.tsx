import type { ReactNode } from "react";

import {
  BOARD_LABEL,
  COLLEGE_TYPE_LABEL,
  COMMISSION_LINKED_NOTE,
  COMMISSION_NOTE,
  display,
  gradeRange,
  labelOf,
  type OrgProfile,
  type Organization,
  PROFILE_GROUP_LABEL,
  PROFILE_LABEL,
  profileGroup,
  SCHOOL_TYPE_LABEL,
  SOURCE_LABEL,
} from "@/lib/bdmOrganizations";

// bdm-003 (spec §6.3, §12.2 F3-F5): the type's details under their own heading inside the Details card, and the definition list both
// sections share. Text nodes only; line breaks via CSS (never innerHTML).
/** A stored multi-line value (P14) with its line breaks kept, or "—". */
export const multiline = (value: string | null): ReactNode => <span style={{ whiteSpace: "pre-line" }}>{display(value)}</span>;
const GRID = { display: "grid", gridTemplateColumns: "minmax(120px, max-content) 1fr", gap: "8px 16px", margin: 0 } as const;

export function DetailList({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl style={GRID}>
      {rows.map(([label, value]) => [
        <dt key={`${label}-t`} className="muted">
          {label}
        </dt>,
        <dd key={`${label}-d`} style={{ margin: 0, overflowWrap: "anywhere" }}>
          {value}
        </dd>,
      ])}
    </dl>
  );
}

function rowsOf(profile: OrgProfile, liveStaff: number | null): [string, ReactNode][] {
  switch (profile.kind) {
    case "agent":
      return [
        [PROFILE_LABEL.country, display(profile.country)],
        [PROFILE_LABEL.territory, display(profile.territory)],
        [PROFILE_LABEL.source, labelOf(SOURCE_LABEL, profile.source)],
        // bdm-019: once linked, the agency's live staff count, with the value the BDM entered kept beside it
        [PROFILE_LABEL.staff_count, liveStaff === null ? display(profile.staff_count) : `${liveStaff} live${profile.staff_count === null ? "" : ` (${profile.staff_count} entered)`}`],
      ];
    case "school":
      return [
        [PROFILE_LABEL.board, labelOf(BOARD_LABEL, profile.board)],
        [PROFILE_LABEL.school_type, labelOf(SCHOOL_TYPE_LABEL, profile.school_type)],
        ["Grades", gradeRange(profile.grade_from, profile.grade_to)], // one row for the form's Lowest / Highest grade
      ];
    case "college":
      return [
        [PROFILE_LABEL.affiliation, display(profile.affiliation)],
        [PROFILE_LABEL.college_type, labelOf(COLLEGE_TYPE_LABEL, profile.college_type)],
        [PROFILE_LABEL.courses, multiline(profile.courses)],
      ];
  }
}

export default function BdmOrganizationProfileDetails({ organization: org }: { organization: Organization }) {
  const group = profileGroup(org.org_type);
  if (!group) return null;
  const name = PROFILE_GROUP_LABEL[group];
  const agent = org.onboarding?.agent ?? null;
  // QA19-02: a linked agency always has a live staff count to show, even when no details were entered
  const filled = org.profile && (agent || Object.entries(org.profile).some(([key, value]) => key !== "kind" && value !== null)) ? org.profile : null;
  return (
    <>
      <h4 style={{ margin: "16px 0 8px" }}>{name} details</h4>
      {filled ? (
        <DetailList rows={rowsOf(filled, agent?.staff_count ?? null)} />
      ) : (
        <p className="muted" style={{ margin: 0 }}>
          No {name.toLowerCase()} details yet.{org.permissions.can_edit ? " Use Edit to add them." : ""}
        </p>
      )}
      {group === "agent" && (
        <p className="muted" style={{ margin: "8px 0 0" }}>
          {agent ? COMMISSION_LINKED_NOTE : COMMISSION_NOTE}
        </p>
      )}
    </>
  );
}
