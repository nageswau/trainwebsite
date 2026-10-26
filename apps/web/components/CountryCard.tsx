import Link from "next/link";
import CountryFlag from "./CountryFlag";
import { flagSrc } from "@/lib/countryFlag";
import type { Country } from "@/lib/types";

// nehn-034 (DEC-SCOPE-284 C2-C5): one destination card for the public page and the student portal. Server-safe and data-only (no
// function props) so both server pages render it. No universities yet (C2): "Coming soon" instead of the count and links to them.
export default function CountryCard({ country, applyHref }: { country: Country; applyHref?: string }) {
  const slug = encodeURIComponent(country.slug);
  const count = country.university_count ?? 0;
  return (
    <article className="card hover">
      <div className="icon-circle">{flagSrc(country.iso2) ? <CountryFlag iso2={country.iso2} size="large" /> : "🌍"}</div>
      <h3>{country.name}</h3>
      <p className="muted">{country.overview}</p>
      <p><span className="badge">{count === 0 ? "Coming soon" : `${count} ${count === 1 ? "university" : "universities"}`}</span></p>
      <p><strong>Indicative tuition:</strong><br />{country.tuition}</p>
      <div className="actions">
        {count > 0 && <Link className="btn small" href={`/overseas/universities?country=${slug}`} aria-label={`View universities in ${country.name}`}>View universities</Link>}
        {count > 0 && applyHref && <Link className="btn small" href={`${applyHref}?country=${slug}`} aria-label={`Apply in ${country.name}`}>Apply</Link>}
        <Link className="btn small secondary" href={`/overseas/countries/${slug}`} aria-label={`Country guide for ${country.name}`}>Country guide</Link>
      </div>
    </article>
  );
}
