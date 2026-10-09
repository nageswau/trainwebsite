import Link from "next/link";

import { contactText, MEETING_STATUSES, MEETING_TYPES, type MeetingRow, meetingPath, meetingWhen, MODES } from "@/lib/meetings";

// upc-009: a page of meetings. Server-rendered; paging is a link built by the caller (it keeps the page's filters). Below 640 px each row
// is a card of labelled lines (globals.css .telecaller-list reads each cell's data-label).
export default function MeetingTable({ items, total, label, showUniversity = true }: { items: MeetingRow[]; total: number; label: string; showUniversity?: boolean }) {
  return (
    <div className="telecaller-list">
      <div className="table-wrap" role="region" aria-label={label} tabIndex={0}>
        <table>
          <caption className="visually-hidden">{label}, {total} in total</caption>
          <thead>
            <tr>
              <th scope="col">Meeting</th>{showUniversity && <th scope="col">University</th>}<th scope="col">Type</th><th scope="col">When (IST)</th>
              <th scope="col">Mode</th><th scope="col">Contact person</th><th scope="col">Responsible</th><th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((m) => (
              <tr key={m.id}>
                <td data-label="Meeting"><Link href={meetingPath(m.id)}>{m.code}</Link></td>
                {showUniversity && <td data-label="University">{m.university.name}</td>}
                <td data-label="Type">{MEETING_TYPES[m.meeting_type] ?? m.meeting_type}</td>
                <td data-label="When (IST)">{meetingWhen(m.starts_at)}</td>
                <td data-label="Mode">{MODES[m.mode] ?? m.mode}{m.warnings.includes("link_missing") ? " · no link yet" : ""}</td>
                <td data-label="Contact person">{contactText(m.contact)}</td>
                <td data-label="Responsible">{m.responsible.full_name}{m.responsible.active ? "" : " (inactive)"}</td>
                <td data-label="Status"><span className="badge">{MEETING_STATUSES[m.status] ?? m.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
