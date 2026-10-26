import PublicShell from "@/components/PublicShell";
import PageHero from "@/components/PageHero";
import CollectionExplorer from "@/components/CollectionExplorer";
import {publicApi} from "@/lib/api";
import type {Country} from "@/lib/types";
import CountryCard from "@/components/CountryCard";

export default async function Countries() {
  let countries: Country[] = [];
  try { countries = await publicApi<Country[]>("/api/v1/public/countries"); } catch {}
  const items = countries.map(country => ({
    id: country.id, searchText: `${country.name} ${country.overview} ${country.tuition} ${country.living_expenses} ${country.work_opportunities} ${country.post_study_work}`,
    filters: {destination: country.name}, sortValues: {name: country.name},
    content: <CountryCard country={country}/>, // nehn-034: flag, count, View universities (DEC-SCOPE-284)
  }));
  return <PublicShell division="overseas"><PageHero eyebrow="Study Abroad" title="Study Destinations" description="Compare country-level study information, indicative costs, visa process, work opportunities and post-study options before building your university shortlist."/><section className="section"><div className="container"><CollectionExplorer items={items} noun="destinations" searchPlaceholder="Search country, costs, or work options…" filters={[{key: "destination", label: "Destination"}]} sorts={[{value: "name", key: "name", label: "Country A–Z"}, {value: "name-desc", key: "name", label: "Country Z–A", direction: "desc"}]} empty={<div className="card"><h3>No destinations available</h3><p className="muted">Published destination guides will appear here.</p></div>}/></div></section><section className="section compact soft"><div className="container"><p className="muted"><strong>Important:</strong> country, fee, visa, work and immigration information in seed data is illustrative. Production content must be verified against current official government and university sources before publication.</p></div></section></PublicShell>;
}
