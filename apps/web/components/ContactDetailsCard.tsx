import Link from "next/link";

// hrc-031 (DEC-SCOPE-412 P10): the Privacy section's contact verification, in both portals. Read-only: the change itself is on the profile.
export default function ContactDetailsCard({ email, verified, pendingEmail, mobile, changeHref }: {
  email: string; verified: boolean; pendingEmail?: string | null; mobile: string | null; changeHref: string;
}) {
  return (
    <section className="action-card" aria-labelledby="contact-details-heading" style={{ display: "grid", gap: 8 }}>
      <h3 id="contact-details-heading" style={{ margin: 0 }}>Contact details</h3>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline", overflowWrap: "anywhere" }}>
        <span className="muted">Email</span> <strong>{email}</strong> <span className="badge">{verified ? "Verified" : "Not verified"}</span>
      </div>
      {pendingEmail && <p className="muted" style={{ margin: 0, overflowWrap: "anywhere" }}>Waiting for you to confirm {pendingEmail} from the link we emailed.</p>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        <span className="muted">Mobile</span> <strong>{mobile || "Not provided"}</strong>
      </div>
      <p style={{ margin: 0 }}><Link className="btn secondary small" href={changeHref}>Change your contact details</Link></p>
    </section>
  );
}
