import Link from "next/link";
import PublicShell from "@/components/PublicShell";
import WebinarRegisterForm from "@/components/WebinarRegisterForm";
import { publicApi } from "@/lib/api";
import type { Webinar } from "@/lib/types";
import LocalTime from "@/components/LocalTime";

// OVS-007: the listing page either linked out to an external registration_url or fell
// back to a generic "Register interest" -> /overseas/contact link, even though the
// backend's registration endpoint (reused from PUB-004, division-agnostic over any
// Event id) already worked here. This detail page reuses that same endpoint/form.
export default async function OverseasEventDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let event: Webinar | null = null;
  try {
    event = await publicApi<Webinar>(`/api/v1/public/webinars/${id}`);
  } catch {}

  if (!event) {
    return (
      <PublicShell division="overseas">
        <section className="section">
          <div className="container">
            <h1>Event not found</h1>
            <Link className="btn" href="/overseas/events">Back to events</Link>
          </div>
        </section>
      </PublicShell>
    );
  }

  return (
    <PublicShell division="overseas">
      <section className="page-hero">
        <div className="container">
          <div className="eyebrow">{event.event_type}</div>
          <h1 style={{ fontSize: "clamp(34px,4vw,54px)" }}>{event.title}</h1>
          <p className="lead"><LocalTime value={event.starts_at} time label /> · {event.location}</p>
        </div>
      </section>
      <section className="section">
        <div className="container" style={{ maxWidth: 820 }}>
          <div className="card">
            <h3>About this event</h3>
            <p>{event.description}</p>
          </div>
          <div className="card" style={{ marginTop: 18 }}>
            {event.is_past ? (
              <>
                <h3>Registration closed</h3>
                <p className="muted">This event has already taken place. Explore upcoming events instead.</p>
                <Link className="btn small" href="/overseas/events">View upcoming events</Link>
              </>
            ) : event.registration_url ? (
              <>
                <h3>Register for this event</h3>
                <p className="muted">Registration for this event is handled by the organiser.</p>
                <a className="btn small" href={event.registration_url}>Register via official link</a>
              </>
            ) : (
              <>
                <h3>Register for this event</h3>
                <WebinarRegisterForm eventId={event.id} label="event" />
              </>
            )}
          </div>
        </div>
      </section>
    </PublicShell>
  );
}
