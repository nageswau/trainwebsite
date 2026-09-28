import { formatCalendarDate } from "@/lib/formatDate";

// ENH-024 -- a Skill India certification's details (docs/superpowers/specs/2026-09-28-enh-024-skill-india-certification-design.md §6).
// Hook-free, so the client PortfolioPanel and the server 360° panels share it; renders nothing for every other entry. Status is a
// text label plus the shared `.status` / `.status pending` classes (lib/skills.ts's convention) -- not StatusChip, whose module
// imports serverApi and would break a client component's build.

export type CertificationFields = { certification_type?: string | null; certification_status?: string | null; certificate_number?: string | null; issued_on?: string | null };

export const CERT_STATUS_LABEL: Record<string, string> = { enrolled: "Enrolled", in_progress: "In progress", certified: "Certified" };

export default function CertificationDetails({ entry }: { entry: CertificationFields }) {
  if (entry.certification_type !== "skill_india") return null;
  const status = entry.certification_status;
  return (
    <div className="pf-cert">
      <span className="badge">Skill India</span>
      {status ? <span className={status === "certified" ? "status" : "status pending"}>{CERT_STATUS_LABEL[status] ?? status}</span> : null}
      {entry.certificate_number ? <span className="muted">Certificate no. {entry.certificate_number}</span> : null}
      {entry.issued_on ? <span className="muted">Issued {formatCalendarDate(entry.issued_on)}</span> : null}
    </div>
  );
}
