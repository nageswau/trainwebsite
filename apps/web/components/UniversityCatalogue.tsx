"use client";

import Link from "next/link";
import CollectionExplorer from "./CollectionExplorer";
import type {University} from "@/lib/types";

export default function UniversityCatalogue({universities}: {universities: University[]}) {
  const items = universities.map(university => ({
    id: university.id,
    searchText: `${university.name} ${university.city} ${university.overview} ${university.eligibility}`,
    filters: {city: university.city},
    sortValues: {name: university.name, city: university.city},
    content: <article className="card hover"><span className="badge">{university.city}</span><h3 style={{marginTop: 14}}>{university.name}</h3><p className="muted">{university.overview}</p><p><strong>Eligibility:</strong> {university.eligibility}</p><Link className="btn small" href={`/overseas/universities/${university.slug}`}>University profile</Link></article>,
  }));
  return <CollectionExplorer items={items} noun="universities" searchPlaceholder="Search university, city, or eligibility…" filters={[{key: "city", label: "City"}]} sorts={[{value: "name-asc", key: "name", label: "University A–Z"}, {value: "name-desc", key: "name", label: "University Z–A", direction: "desc"}, {value: "city-asc", key: "city", label: "City A–Z"}]} empty={<div className="card"><h3>No universities available</h3><p>Ask a counselor to shortlist universities for your profile.</p><Link className="btn" href="/overseas/contact">Profile evaluation</Link></div>}/>;
}
