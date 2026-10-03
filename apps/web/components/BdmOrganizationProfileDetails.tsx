import type { ReactNode } from "react";

import {
  BOARD_LABEL,
  COLLEGE_TYPE_LABEL,
  display,
  gradeRange,
  labelOf,
  type OrgProfile,
  type Organization,
  PROFILE_GROUP_LABEL,
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

function rowsOf(profile: OrgProfile): [string, ReactNode][] {
  switch (profile.kind) {
    case "agent":
      return [
        ["Country", display(profile.country)],
        ["Territory", display(profile.territory)],
        ["Source", labelOf(SOURCE_LABEL, profile.source)],
        ["Number of staff", display(profile.staff_count)],
      ];
    case "school":
      return [
        ["Board", labelOf(BOARD_LABEL, profile.board)],
        ["School type", labelOf(SCHOOL_TYPE_LABEL, profile.school_type)],
        ["Grades", gradeRange(profile.grade_from, profile.grade_to)],
      ];
    case "college":
      return [
        ["University / affiliation", display(profile.affiliation)],
        ["College type", labelOf(COLLEGE_TYPE_LABEL, profile.college_type)],
        ["Courses", multiline(profile.courses)],
      ];
  }
}

export default function BdmOrganizationProfileDetails({ organization: org }: { organization: Organization }) {
  const group = profileGroup(org.org_type);
  if (!group) return null;
  const name = PROFILE_GROUP_LABEL[group];
  const filled = org.profile && Object.entries(org.profile).some(([key, value]) => key !== "kind" && value !== null) ? org.profile : null;
  return (
    <>
      <h4 style={{ margin: "16px 0 8px" }}>{name} details</h4>
      {filled ? (
        <DetailList rows={rowsOf(filled)} />
      ) : (
        <p className="muted" style={{ margin: 0 }}>
          No {name.toLowerCase()} details yet.{org.permissions.can_edit ? " Use Edit to add them." : ""}
        </p>
      )}
      {group === "agent" && (
        <p className="muted" style={{ margin: "8px 0 0" }}>
          Commission: Available after onboarding
        </p>
      )}
    </>
  );
}
