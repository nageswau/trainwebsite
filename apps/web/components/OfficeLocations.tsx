import { mapsUrl, OFFICES } from "@/lib/offices";

// PUB-024 (DEC-SCOPE-223): one card per office with a "Get directions" link to Google Maps (new tab).
// Server-safe; the heading level follows the host page so the outline stays correct.
type Level = 2 | 3;

export default function OfficeLocations({ title = "Our offices", headingLevel = 2 }: { title?: string; headingLevel?: Level }) {
  const Title = `h${headingLevel}` as const;
  const City = `h${headingLevel + 1}` as "h3" | "h4";
  return (
    <section className="office-locations" aria-label={title}>
      <Title>{title}</Title>
      <div className="grid three office-grid">
        {OFFICES.map((office) => (
          <article className="card" key={office.city}>
            <City>{office.city}</City>
            <address className="muted">{office.address}</address>
            <a className="btn secondary small" href={mapsUrl(office.address)} target="_blank" rel="noopener noreferrer">
              Get directions<span className="visually-hidden"> to the {office.city} office (opens in a new tab)</span>
            </a>
          </article>
        ))}
      </div>
    </section>
  );
}
