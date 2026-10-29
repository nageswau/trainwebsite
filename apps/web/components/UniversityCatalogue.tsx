"use client";

import Link from "next/link";
import CollectionExplorer from "./CollectionExplorer";
import CountryFlag from "./CountryFlag";
import UniversityLogo from "./UniversityLogo";
import type {University} from "@/lib/types";

// nehn-035 (DEC-SCOPE-328 L7, L8): each card adds the country (flag + name) beside the city, "N programs", View details and Apply, and
// the controls a Country filter. Apply opens the student's apply form with the university preselected (logged out: login first, then
// back); it is hidden while the university lists no programs, and not prefetched (signed out, that would only fetch a login redirect).
function programs(count: number) {
  return count === 0 ? "Programs coming soon" : `${count} ${count === 1 ? "program" : "programs"}`;
}

export default function UniversityCatalogue({universities}: {universities: University[]}) {
  const items = universities.map(university => {
    const count = university.programs_count ?? 0;
    const slug = encodeURIComponent(university.slug);
    return {
      id: university.id,
      searchText: `${university.name} ${university.city} ${university.country_name ?? ""} ${university.overview} ${university.eligibility}`,
      filters: {city: university.city, country: university.country_name ?? ""},
      sortValues: {name: university.name, city: university.city},
      content: <article className="card hover"><div style={{display: "flex", alignItems: "center", gap: 12}}><UniversityLogo name={university.name} logoUrl={university.logo_url}/><span className="badge" style={{display: "inline-flex", alignItems: "center", gap: 6}}><CountryFlag iso2={university.country_iso2}/>{[university.city, university.country_name].filter(Boolean).join(", ")}</span></div><h3 style={{marginTop: 14}}>{university.name}</h3><p className="muted">{university.overview}</p><p><strong>Eligibility:</strong> {university.eligibility}</p><p><span className="badge">{programs(count)}</span></p><div className="actions"><Link className="btn small secondary" href={`/overseas/universities/${slug}`} aria-label={`View details for ${university.name}`}>View details</Link>{count > 0 && <Link className="btn small" href={`/overseas/student/applications?university=${slug}`} prefetch={false} aria-label={`Apply to ${university.name}`}>Apply</Link>}</div></article>,
    };
  });
  return <CollectionExplorer items={items} noun="universities" searchPlaceholder="Search university, city, or eligibility…" filters={[{key: "country", label: "Country", allLabel: "All countries"}, {key: "city", label: "City"}]} sorts={[{value: "name-asc", key: "name", label: "University A–Z"}, {value: "name-desc", key: "name", label: "University Z–A", direction: "desc"}, {value: "city-asc", key: "city", label: "City A–Z"}]} empty={<div className="card"><h3>No universities available</h3><p>Ask a counselor to shortlist universities for your profile.</p><Link className="btn" href="/overseas/contact">Profile evaluation</Link></div>}/>;
}
