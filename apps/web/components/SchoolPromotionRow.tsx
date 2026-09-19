import { memo } from "react";
import styles from "./SchoolPromotionPanel.module.css";

export type PromotionStudent = { id: string; student_code: string; full_name: string; grade_or_class: string | null; grade_level: number | null; academic_year_id: string | null };
export type PromotionAction = "promote" | "hold_back";
export type PromotionRowResult = { student_id: string; status: "promoted" | "held_back" | "failed" | "skipped"; reason: string | null; message: string | null; grade_level: number | null; grade_or_class: string | null };

type Props = {
  student: PromotionStudent;
  activeYearLabel: string;
  inActiveYear: boolean;
  selected: boolean;
  action: PromotionAction;
  override: string;
  result: PromotionRowResult | null;
  onSelect: (id: string, on: boolean) => void;
  onAction: (id: string, action: PromotionAction) => void;
  onOverride: (id: string, value: string) => void;
};

// Advisory only: the server decides (spec §5.2). It just spares the coordinator a predictable failed row.
function promoteHint(level: number | null) {
  if (level === null) return "Grade level is not set. Set it on the roster before promoting.";
  if (level >= 12) return "Grade 12 is the highest grade and cannot be promoted. Choose Hold back.";
  return null;
}

// One student. Memoised with primitive props and stable callbacks so ticking one box does not re-render
// the whole roster. Labels are real <label>s (visible on mobile, moved to a header row from 768px up).
function SchoolPromotionRow({ student, activeYearLabel, inActiveYear, selected, action, override, result, onSelect, onAction, onOverride }: Props) {
  const id = student.id;
  const settled = result && (result.status === "promoted" || result.status === "held_back") ? result : null;
  const locked = inActiveYear || settled !== null;
  const gradeText = settled ? settled.grade_or_class : student.grade_or_class;
  const level = settled ? settled.grade_level : student.grade_level;
  const hint = locked || action !== "promote" ? null : promoteHint(student.grade_level);
  const failure = result && (result.status === "failed" || result.status === "skipped") ? result : null;
  const describedBy = failure ? `promo-msg-${id}` : hint ? `promo-hint-${id}` : undefined;

  return (
    <li className={styles.row}>
      <div className={styles.who}>
        <input id={`promo-select-${id}`} type="checkbox" checked={selected && !locked} disabled={locked} onChange={(e) => onSelect(id, e.target.checked)} />
        <label htmlFor={`promo-select-${id}`}>
          <strong>{student.full_name}</strong>
          <span className="muted">{student.student_code} · {gradeText || "Grade not set"}{level !== null ? ` (level ${level})` : ""}</span>
        </label>
      </div>
      {locked ? (
        <div className={`${styles.outcome} ${styles.outcomeWide}`}>
          {settled ? <span className="status">{settled.status === "promoted" ? "Promoted" : "Held back"}</span> : null}
          <span>{settled ? `Now in ${activeYearLabel}` : `Already in ${activeYearLabel}`}</span>
        </div>
      ) : (
        <>
          <div className={`field ${styles.control}`}>
            <label className={styles.controlLabel} htmlFor={`promo-action-${id}`}>Action</label>
            <select id={`promo-action-${id}`} className="select" value={action} aria-describedby={describedBy} onChange={(e) => onAction(id, e.target.value as PromotionAction)}>
              <option value="promote">Promote</option>
              <option value="hold_back">Hold back</option>
            </select>
          </div>
          <div className={`field ${styles.control}`}>
            <label className={styles.controlLabel} htmlFor={`promo-label-${id}`}>New label (optional)</label>
            <input id={`promo-label-${id}`} type="text" className="search" placeholder="automatic" maxLength={60} value={override} disabled={action !== "promote"} aria-describedby={describedBy} onChange={(e) => onOverride(id, e.target.value)} />
          </div>
          <div className={styles.outcome}>
            {failure ? (
              <>
                <span className={failure.status === "failed" ? "status error" : "status pending"}>{failure.status === "failed" ? "Not changed" : "Skipped"}</span>
                <span id={`promo-msg-${id}`}>{failure.message}</span>
              </>
            ) : hint ? (
              <span id={`promo-hint-${id}`} className={styles.hint}>{hint}</span>
            ) : null}
          </div>
        </>
      )}
    </li>
  );
}

export default memo(SchoolPromotionRow);
