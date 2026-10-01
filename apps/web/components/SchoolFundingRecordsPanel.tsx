"use client";

import { useState } from "react";
import FormMessage from "@/components/FormMessage";
import FundingRecordForm from "@/components/FundingRecordForm";
import { refocus } from "@/lib/focus";
import { formatCalendarDate } from "@/lib/formatDate";
import { type FundingRecord, isFinal, stageText, statusClass, SUPPORT_TYPE_LABEL } from "@/lib/fundingRecords";

type Student = { id: string; full_name: string; school_name: string };

const COLUMNS = ["Student", "Support type", "Stage", "Since", "Provider", "Actions"] as const;

// ENH-020 (spec §6): the counsellor's cases. Open cases come first because they are the work; finished cases (Completed/Closed) are
// read-only history in a collapsed section. Editing opens inline with focus on its heading and returns focus to the row's button.
export default function SchoolFundingRecordsPanel({ records, students }: { records: FundingRecord[]; students: Student[] }) {
  const [editing, setEditing] = useState<FundingRecord | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const open = records.filter((r) => !isFinal(r.status));
  const finished = records.filter((r) => isFinal(r.status));

  function studentName(id: string) {
    return students.find((s) => s.id === id)?.full_name || "Unknown student";
  }

  function caseName(r: FundingRecord) {
    return `${SUPPORT_TYPE_LABEL[r.support_type].toLowerCase()} case for ${studentName(r.school_student_id)}`;
  }

  function startEdit(r: FundingRecord) {
    setNotice(null);
    setEditing(r);
    refocus("funding-edit-heading");
  }

  function close() {
    const id = editing?.id;
    setEditing(null);
    if (id) refocus(`funding-edit-${id}`);
  }

  // Final review I1/I2: the panel announces the save (the edit form is gone by then) and, when the case became final, moves focus to
  // the Open cases heading -- its row, and so its Edit button, leaves the open table on the refresh.
  function saved(record: FundingRecord) {
    setEditing(null);
    setNotice("Case saved.");
    refocus(isFinal(record.status) ? "funding-open-heading" : `funding-edit-${record.id}`);
  }

  return (
    <div className="portal-content card-stack funding-panel">
      <div className="card">
        <h2>Funding support</h2>
        <p className="muted">Education loans, financial assistance, scholarships and funding guidance for your students.</p>
        <h3 id="funding-open-heading" tabIndex={-1}>Open cases</h3>
        {notice && <FormMessage message={{ text: notice, failed: false }} />}
        {open.length === 0 ? (
          <p className="muted">{records.length === 0 ? "No funding support cases yet. Add one below when a student needs a loan, scholarship or funding guidance." : "No open cases."}</p>
        ) : (
          <div className="table-wrap">
            <table className="table funding-records" aria-labelledby="funding-open-heading">
              <thead>
                <tr>{COLUMNS.map((c) => <th key={c} scope="col">{c === "Actions" ? <span className="visually-hidden">Actions</span> : c}</th>)}</tr>
              </thead>
              <tbody>
                {open.map((r) => (
                  <tr key={r.id}>
                    <td data-label="Student">{studentName(r.school_student_id)}</td>
                    <td data-label="Support type">{SUPPORT_TYPE_LABEL[r.support_type]}</td>
                    <td data-label="Stage"><span className={statusClass(r.status)}>{stageText(r.status)}</span></td>
                    <td data-label="Since">{formatCalendarDate(r.status_changed_on)}</td>
                    <td data-label="Provider">{r.provider_name || "—"}</td>
                    <td data-label="Actions">
                      <button id={`funding-edit-${r.id}`} type="button" className="btn secondary small" onClick={() => startEdit(r)}>
                        Edit<span className="visually-hidden"> {caseName(r)}</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {finished.length > 0 && (
          <details className="funding-finished">
            <summary>Finished cases ({finished.length})</summary>
            {finished.map((r) => (
              <dl className="record-details" key={r.id}>
                <div className="record-details-row"><dt>Student</dt><dd>{studentName(r.school_student_id)}</dd></div>
                <div className="record-details-row"><dt>Support type</dt><dd>{SUPPORT_TYPE_LABEL[r.support_type]}</dd></div>
                <div className="record-details-row"><dt>Outcome</dt><dd><span className={statusClass(r.status)}>{stageText(r.status)}</span> on {formatCalendarDate(r.status_changed_on)}</dd></div>
                {r.closure_reason && <div className="record-details-row"><dt>Reason</dt><dd>{r.closure_reason}</dd></div>}
              </dl>
            ))}
          </details>
        )}
      </div>

      {editing && (
        <div className="action-card">
          <h3 id="funding-edit-heading" tabIndex={-1} onKeyDown={(e) => { if (e.key === "Escape") close(); }}>
            Update {studentName(editing.school_student_id)}&apos;s {SUPPORT_TYPE_LABEL[editing.support_type].toLowerCase()} case
          </h3>
          <FundingRecordForm key={editing.id} students={students} record={editing} onDone={saved} onCancel={close} />
        </div>
      )}

      <div className="action-card">
        <h3>Add a case</h3>
        {students.length === 0 ? (
          <p className="muted">No students in your portfolio yet. Contact your Overseas Admin.</p>
        ) : (
          <FundingRecordForm students={students} onDone={() => undefined} onCancel={() => undefined} />
        )}
      </div>
    </div>
  );
}
