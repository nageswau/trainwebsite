"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import CourseForm from "@/components/CourseForm";
import CourseImportPanel from "@/components/CourseImportPanel";
import { commissionText, type Course, type CourseOptions, type CoursePage, COURSES_PATH, englishText, moneyText } from "@/lib/courseMaster";
import { dateText } from "@/lib/universityAgreements";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// upc-017 (§16): a university's courses & programmes on its master page -- "counselors know exactly what each partner university offers".
// Every reader sees the list (inactive ones marked, CO11); writers add, edit and import (CO1). The commission row appears only when the
// API sent it, which it does for the commission roles alone (U2). Every success re-reads the page (router.refresh).
function facts(c: Course): [string, string | null][] {
  return [
    ["Category", c.category],
    ["Duration", c.duration],
    ["Intakes", c.intake || null],
    ["Tuition fee", c.tuition_fee || null],
    ["Application fee", moneyText(c.application_fee, c.application_fee_currency)],
    ["English", englishText(c)],
    ["Entry requirements", c.entry_requirements],
    ["Application process", c.application_process],
    ["Deadline", c.deadline && dateText(c.deadline)],
    ["Scholarships", c.scholarships.map((s) => `${s.title} (${s.amount})`).join(", ") || null],
    ...("commission" in c ? [["Commission (restricted)", commissionText(c.commission)] as [string, string]] : []),
  ];
}

export default function UniversityCourses({ universityId, page, options, canSetCommission }: {
  universityId: string; page: CoursePage; options: CourseOptions | null; canSetCommission: boolean;
}) {
  const router = useRouter();
  const [open, setOpen] = useState<string | null>(null); // "new", "import", "<id>", or null
  const [notice, setNotice] = useState<string | null>(null);
  const focus = useFocusAfterRender();
  const canWrite = page.can_edit && options !== null;
  const show = (key: string | null) => {
    setOpen(key);
    setNotice(null);
  };
  const done = (message: string) => {
    show(null);
    setNotice(message);
    focus("courses-add", "uni-courses"); // the control that had focus is gone
    router.refresh();
  };

  return (
    <section className="action-card wide" aria-labelledby="uni-courses">
      <h3 id="uni-courses" tabIndex={-1}>Courses &amp; programmes</h3>
      {page.total === 0 && open !== "new" && <p className="muted">No courses recorded yet.</p>}
      {page.items.length > 0 && (
        <ul className="list-clean" aria-label="Courses" style={{ display: "grid", gap: 14 }}>
          {page.items.map((c) => (
            <li key={c.id} style={{ display: "grid", gap: 6, borderTop: "1px solid var(--line, #e5e7eb)", paddingTop: 10 }}>
              <p style={{ margin: 0, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
                <strong>{c.title}</strong> <span className="badge">{c.level}</span>
                {!c.active && <span className="badge">Inactive</span>}
              </p>
              <dl style={{ display: "grid", gridTemplateColumns: "minmax(120px, max-content) 1fr", gap: "4px 16px", margin: 0 }}>
                {facts(c).filter(([, value]) => value).map(([term, value]) => [
                  <dt key={`${term}-t`} className="muted">{term}</dt>,
                  <dd key={`${term}-d`} style={{ margin: 0, overflowWrap: "anywhere", whiteSpace: "pre-line" }}>{value}</dd>,
                ])}
              </dl>
              {canWrite && c.permissions.can_edit && (open === c.id ? (
                <CourseForm universityId={universityId} options={options} course={c} canSetCommission={canSetCommission} label={`Edit ${c.title}`} onSaved={done} onCancel={() => show(null)} />
              ) : (
                <div className="actions">
                  <button type="button" className="btn ghost small" onClick={() => show(c.id)}>Edit<span className="visually-hidden"> {c.title}</span></button>
                </div>
              ))}
            </li>
          ))}
        </ul>
      )}
      {page.total > page.items.length && (
        <p className="muted">Showing {page.items.length} of {page.total}. <Link href={COURSES_PATH}>All courses &amp; programmes</Link></p>
      )}
      {canWrite && open === "new" && (
        <CourseForm universityId={universityId} options={options} canSetCommission={canSetCommission} label="New course" onSaved={done} onCancel={() => show(null)} />
      )}
      {canWrite && open === "import" && <CourseImportPanel universityId={universityId} />}
      {canWrite && open !== "new" && (
        <div className="actions" style={{ marginTop: 12 }}>
          <button id="courses-add" type="button" className="btn secondary small" onClick={() => show("new")}>Add course</button>
          <button type="button" className="btn ghost small" aria-expanded={open === "import"} onClick={() => show(open === "import" ? null : "import")}>
            {open === "import" ? "Close import" : "Import courses (CSV)"}
          </button>
        </div>
      )}
      {notice && <p className="muted" role="status">{notice}</p>}
    </section>
  );
}
