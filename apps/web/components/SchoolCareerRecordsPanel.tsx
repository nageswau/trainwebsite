"use client";

import { useState } from "react";
import CareerPreferencesCard from "@/components/CareerPreferencesCard";
import CareerRecordForm from "@/components/CareerRecordForm";
import { type CareerRecord, RECORD_TYPE_LABEL, statusLabel } from "@/lib/careerRecords";
import { refocus } from "@/lib/focus";
import { formatCalendarDate } from "@/lib/formatDate";

type Student = { id: string; full_name: string; school_name: string };

// SCH-004 + ENH-026: the Career Counselor's records -- visible to readers immediately (no Draft/Published gate). ENH-026 adds the
// §7 status and structured fields, and inline editing (spec §11.2 F2): opening moves focus to the form heading, closing returns
// it to the row's Edit button.
export default function SchoolCareerRecordsPanel({ records, students }: { records: CareerRecord[]; students: Student[] }) {
  const [editing, setEditing] = useState<CareerRecord | null>(null);

  function studentName(id: string) {
    return students.find((s) => s.id === id)?.full_name || "Unknown student";
  }

  function open(record: CareerRecord) {
    setEditing(record);
    refocus("career-edit-heading");
  }

  function close() {
    const id = editing?.id;
    setEditing(null);
    if (id) refocus(`career-edit-${id}`);
  }

  return (
    <div className="portal-content">
      <div className="card">
        <h2>Records</h2>
        {records.length === 0 ? (
          <p className="muted">No career guidance or counselling recorded yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Student</th><th>Type</th><th>Status</th><th>Next follow-up</th><th>Notes</th><th><span className="visually-hidden">Actions</span></th></tr>
              </thead>
              <tbody>
                {records.map((r) => (
                  <tr key={r.id}>
                    <td>{studentName(r.school_student_id)}</td>
                    <td>{RECORD_TYPE_LABEL[r.record_type] || r.record_type}</td>
                    <td>{r.record_type === "recommendation" ? "—" : <span className={`status${r.status === "completed" ? "" : " pending"}`}>{statusLabel(r.status)}</span>}</td>
                    <td>{r.next_follow_up_date ? formatCalendarDate(r.next_follow_up_date) : "—"}</td>
                    <td>{r.notes}</td>
                    <td>
                      <button id={`career-edit-${r.id}`} type="button" className="btn secondary small" onClick={() => open(r)}>
                        Edit<span className="visually-hidden"> record for {studentName(r.school_student_id)}</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {editing && (
        <div className="action-card">
          <h3 id="career-edit-heading" tabIndex={-1}>Edit record for {studentName(editing.school_student_id)}</h3>
          <CareerRecordForm key={editing.id} students={students} record={editing} onDone={close} onCancel={close} />
        </div>
      )}

      <div className="action-card">
        <h3>Add a record</h3>
        {students.length === 0 ? (
          <p className="muted">No students in your portfolio yet. Contact your Overseas Admin.</p>
        ) : (
          <CareerRecordForm students={students} onDone={() => undefined} onCancel={() => undefined} />
        )}
      </div>

      <CareerPreferencesCard students={students} />
    </div>
  );
}
