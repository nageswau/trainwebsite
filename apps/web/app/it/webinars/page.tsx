import Link from "next/link";
import PublicShell from "@/components/PublicShell";
import PageHero from "@/components/PageHero";
import { publicApi } from "@/lib/api";
import type { Webinar } from "@/lib/types";
import LocalTime from "@/components/LocalTime";

export default async function Webinars() {
  let webinars: Webinar[] = [];
  try {
    webinars = await publicApi<Webinar[]>("/api/v1/public/webinars?division=it");
  } catch {}

  const upcoming = webinars.filter((w) => !w.is_past);
  const past = webinars.filter((w) => w.is_past);

  return (
    <PublicShell division="it">
      <PageHero
        eyebrow="Webinars"
        title="Live sessions on careers, skills, and hiring"
        description="Join a free webinar to hear from trainers and industry panels before you enrol, or catch up on what past sessions covered."
      />
      <section className="section">
        <div className="container">
          <h2>Upcoming</h2>
          {upcoming.length === 0 ? (
            <div className="card">
              <h3>No upcoming webinars right now</h3>
              <p className="muted">Check back soon, or explore our programmes in the meantime.</p>
            </div>
          ) : (
            <div className="grid two" style={{ marginTop: 18 }}>
              {upcoming.map((w) => (
                <article className="card" key={w.id}>
                  <span className="badge">{w.event_type}</span>
                  <h3 style={{ marginTop: 12 }}>{w.title}</h3>
                  <p className="muted"><LocalTime value={w.starts_at} time label /> · {w.location}</p>
                  <p>{w.description}</p>
                  <Link className="btn small" href={`/it/webinars/${w.id}`}>View & register</Link>
                </article>
              ))}
            </div>
          )}
        </div>
      </section>
      {past.length > 0 && (
        <section className="section soft">
          <div className="container">
            <h2>Past webinars</h2>
            <div className="grid two" style={{ marginTop: 18 }}>
              {past.map((w) => (
                <article className="card" key={w.id}>
                  <span className="badge">{w.event_type}</span>
                  <h3 style={{ marginTop: 12 }}>{w.title}</h3>
                  <p className="muted"><LocalTime value={w.starts_at} time label /> · {w.location}</p>
                  <Link className="btn small" href={`/it/webinars/${w.id}`}>View details</Link>
                </article>
              ))}
            </div>
          </div>
        </section>
      )}
    </PublicShell>
  );
}
