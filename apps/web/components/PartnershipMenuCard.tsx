import { PARTNERSHIP_MENU } from "@/lib/navigation";

// upc-001 (PU8): the §32 menu areas that have not landed yet, as plain text -- so the manager sees what the CRM will hold without any
// link to a page that does not exist. Each area moves to the sidebar when its item sets `live`.
export default function PartnershipMenuCard() {
  const upcoming = PARTNERSHIP_MENU.filter((e) => !e.live);
  if (upcoming.length === 0) return null;
  return (
    <section className="card" style={{ padding: 16, marginTop: 16 }} aria-labelledby="partnership-menu-title">
      <h3 id="partnership-menu-title" style={{ marginTop: 0 }}>Coming soon to your CRM</h3>
      <ul style={{ margin: 0, paddingLeft: 20, columns: "14rem", columnGap: 24 }}>
        {upcoming.map((e) => <li key={e.href}>{e.label}</li>)}
      </ul>
    </section>
  );
}
