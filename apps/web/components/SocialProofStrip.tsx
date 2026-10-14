import { publicApi } from "@/lib/api";
import { asOfLabel, initials, socialProofPath, starsLabel, type SocialProof, type SocialProofDivision } from "@/lib/socialProof";

// PUB-022 (DEC-SCOPE-210 SP7): the homepage rating badge + featured testimonials. Everything shown is published and
// consented (the API filters); with nothing published, or when the API is down, the section is not rendered at all.
export default async function SocialProofStrip({ division }: { division: SocialProofDivision }) {
  let data: SocialProof | null = null;
  try {
    data = await publicApi<SocialProof>(socialProofPath(division));
  } catch {
    data = null;
  }
  return <SocialProofView data={data} />;
}

function Stars({ rating }: { rating: number }) {
  const full = Math.round(rating);
  return (
    <span role="img" aria-label={starsLabel(rating)} style={{ color: "#f5a400", letterSpacing: 2 }}>
      {"★".repeat(full)}
      <span style={{ color: "#c9d3e1" }}>{"★".repeat(5 - full)}</span>
    </span>
  );
}

export function SocialProofView({ data }: { data: SocialProof | null }) {
  if (!data || (!data.badge && data.testimonials.length === 0)) return null;
  const { badge, testimonials } = data;
  return (
    <section className="section soft" aria-labelledby="social-proof-title">
      <div className="container">
        <div className="eyebrow">What our students say</div>
        <h2 id="social-proof-title">Trusted by learners and families</h2>
        {badge && (
          <p className="social-proof-badge">
            <Stars rating={badge.rating} /> <strong>{badge.rating.toFixed(1)}</strong> on {badge.source_name} · {badge.review_count.toLocaleString("en-IN")} reviews · as of {asOfLabel(badge.as_of)}
            {badge.review_url && (
              <>
                {" · "}
                <a href={badge.review_url} target="_blank" rel="noopener noreferrer">
                  Read reviews<span className="visually-hidden"> (opens in a new tab)</span>
                </a>
              </>
            )}
          </p>
        )}
        {testimonials.length > 0 && (
          <div className="grid three" style={{ marginTop: 24 }}>
            {testimonials.map((t) => (
              <figure className="card social-proof-card" key={t.id}>
                <Stars rating={t.rating} />
                <blockquote>&ldquo;{t.quote}&rdquo;</blockquote>
                <figcaption>
                  {t.photo_url ? (
                    // eslint-disable-next-line @next/next/no-img-element -- streamed from the API; dimensions are fixed
                    <img src={t.photo_url} alt={`Photo of ${t.person_name}`} width={44} height={44} loading="lazy" />
                  ) : (
                    <span className="social-proof-initials" aria-hidden="true">{initials(t.person_name)}</span>
                  )}
                  <span>
                    <strong>{t.person_name}</strong>
                    {t.context && <span className="muted"> · {t.context}</span>}
                  </span>
                </figcaption>
              </figure>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
