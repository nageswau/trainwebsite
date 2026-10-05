import Link from "next/link";
import PublicShell from "@/components/PublicShell";
import WebinarRegisterForm from "@/components/WebinarRegisterForm";
import { publicApi } from "@/lib/api";
import type { Webinar } from "@/lib/types";
import LocalTime from "@/components/LocalTime";

export default async function WebinarDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let webinar: Webinar | null = null;
  try {
    webinar = await publicApi<Webinar>(`/api/v1/public/webinars/${id}`);
  } catch {}

  if (!webinar) {
    return (
      <PublicShell division="it">
        <section className="section">
          <div className="container">
            <h1>Webinar not found</h1>
            <Link className="btn" href="/it/webinars">Back to webinars</Link>
          </div>
        </section>
      </PublicShell>
    );
  }

  return (
    <PublicShell division="it">
      <section className="page-hero">
        <div className="container">
          <div className="eyebrow">{webinar.event_type}</div>
          <h1 style={{ fontSize: "clamp(34px,4vw,54px)" }}>{webinar.title}</h1>
          <p className="lead"><LocalTime value={webinar.starts_at} time label /> · {webinar.location}</p>
        </div>
      </section>
      <section className="section">
        <div className="container" style={{ maxWidth: 820 }}>
          <div className="card">
            <h3>About this session</h3>
            <p>{webinar.description}</p>
          </div>
          <div className="card" style={{ marginTop: 18 }}>
            {webinar.is_past ? (
              <>
                <h3>Registration closed</h3>
                <p className="muted">This webinar has already taken place. Explore upcoming sessions instead.</p>
                <Link className="btn small" href="/it/webinars">View upcoming webinars</Link>
              </>
            ) : (
              <>
                <h3>Register for this webinar</h3>
                <WebinarRegisterForm eventId={webinar.id} />
              </>
            )}
          </div>
        </div>
      </section>
    </PublicShell>
  );
}
