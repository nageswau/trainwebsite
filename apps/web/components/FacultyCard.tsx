import Link from "next/link";

import type { FacultyView } from "@/lib/faculty";

/** itc-019 (DEC-SCOPE-345): one trainer as a student sees them. Every optional field is only present when the trainer shows it. Plain
 *  text throughout (the bio is never rendered as HTML). Data-only props, so it renders in server and client components alike. */
export default function FacultyCard({ faculty }: { faculty: FacultyView }) {
  const initials = faculty.name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join("");
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 14, alignItems: "flex-start" }}>
      {faculty.photo_url ? (
        // eslint-disable-next-line @next/next/no-img-element -- a short-lived signed link from the API, not a static asset
        <img src={faculty.photo_url} alt={`Photo of ${faculty.name}`} width={72} height={72} style={{ width: 72, height: 72, borderRadius: "50%", objectFit: "cover", flex: "none" }} />
      ) : (
        <span aria-hidden="true" style={{ width: 72, height: 72, borderRadius: "50%", display: "grid", placeItems: "center", background: "var(--surface-2, #eef2f7)", fontWeight: 800, fontSize: 22, flex: "none" }}>{initials}</span>
      )}
      <div style={{ display: "grid", gap: 6, minWidth: 0, flex: "1 1 14rem" }}>
        <div>
          <h4 style={{ margin: 0, fontSize: 17 }}>{faculty.name}</h4>
          {faculty.designation && <p className="muted" style={{ margin: 0, fontSize: 14 }}>{faculty.designation}</p>}
        </div>
        {faculty.expertise.length > 0 && (
          <ul aria-label="Expertise" style={{ display: "flex", flexWrap: "wrap", gap: 6, listStyle: "none", margin: 0, padding: 0 }}>
            {faculty.expertise.map((tag) => <li key={tag} className="badge">{tag}</li>)}
          </ul>
        )}
        {faculty.bio && <p style={{ margin: 0, fontSize: 14, whiteSpace: "pre-line", overflowWrap: "anywhere" }}>{faculty.bio}</p>}
        <dl className="faculty-contact" style={{ display: "grid", gridTemplateColumns: "max-content 1fr", gap: "4px 12px", margin: 0, fontSize: 14 }}>
          {faculty.office_hours && <><dt className="muted">Office hours</dt><dd style={{ margin: 0 }}>{faculty.office_hours}</dd></>}
          {faculty.email && <><dt className="muted">Email</dt><dd style={{ margin: 0, overflowWrap: "anywhere" }}><a href={`mailto:${faculty.email}`}>{faculty.email}</a></dd></>}
          {faculty.phone && <><dt className="muted">Phone</dt><dd style={{ margin: 0 }}><a href={`tel:${faculty.phone.replace(/[^\d+]/g, "")}`}>{faculty.phone}</a></dd></>}
          <dt className="muted">Contact</dt>
          <dd style={{ margin: 0 }}>{faculty.contact_route === "in_app" ? <>Ask through the <Link href="/it/student/questions">Questions page</Link>.</> : `Preferred: ${faculty.contact_route}.`}</dd>
        </dl>
      </div>
    </div>
  );
}
