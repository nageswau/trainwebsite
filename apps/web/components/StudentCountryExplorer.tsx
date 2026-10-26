import CollectionExplorer from "./CollectionExplorer";
import CountryCard from "./CountryCard";
import { publicApi } from "@/lib/api";
import type { Country, PortalPayload } from "@/lib/types";

// nehn-034 (DEC-SCOPE-286 C5): the overseas student's Explore Countries page -- the public destination cards, each with Apply
// (the apply form with that country preselected). The portal payload is header-only; it gates the page and gives the heading.
export default async function StudentCountryExplorer({ data }: { data: PortalPayload }) {
  let countries: Country[] | null = null;
  try {
    countries = await publicApi<Country[]>("/api/v1/public/countries");
  } catch {}
  const items = (countries ?? []).map((country) => ({
    id: country.id,
    searchText: `${country.name} ${country.overview}`,
    sortValues: { name: country.name, count: country.university_count ?? 0 },
    content: <CountryCard country={country} applyHref="/overseas/student/applications" />,
  }));
  return (
    <div className="portal-content">
      <div className="portal-title"><div><div className="eyebrow">Workspace</div><h2>{data.title}</h2><p className="muted">{data.subtitle}</p></div></div>
      {countries === null ? (
        <div className="card" role="alert"><h3>Destinations could not be loaded</h3><p className="muted">Refresh the page to try again.</p></div>
      ) : (
        <CollectionExplorer
          items={items}
          noun="destinations"
          searchPlaceholder="Search country…"
          sorts={[{ value: "name", key: "name", label: "Country A–Z" }, { value: "count", key: "count", label: "Most universities", direction: "desc" }]}
          empty={<div className="card"><h3>No destinations available</h3><p className="muted">Published destination guides will appear here.</p></div>}
        />
      )}
    </div>
  );
}
