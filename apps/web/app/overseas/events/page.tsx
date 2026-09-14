import PublicShell from "@/components/PublicShell";
import PageHero from "@/components/PageHero";
import CollectionExplorer from "@/components/CollectionExplorer";
import {publicApi} from "@/lib/api";

export default async function Events() {
  let events: any[] = [];
  try { events = await publicApi<any[]>("/api/v1/public/events?division=overseas"); } catch {}
  const items = events.map(event => ({
    id: String(event.id), searchText: `${event.title} ${event.description} ${event.event_type} ${event.location}`,
    filters: {type: event.event_type, location: event.location}, sortValues: {title: event.title, starts: event.starts_at},
    content: <div className="card"><span className="badge">{event.event_type}</span><h3 style={{marginTop: 12}}>{event.title}</h3><p className="muted">{new Date(event.starts_at).toLocaleString("en-GB")} · {event.location}</p><p>{event.description}</p><a className="btn small" href={`/overseas/events/${event.id}`}>View & register</a></div>,
  }));
  return <PublicShell division="overseas"><PageHero eyebrow="Events" title="Education Fairs, Webinars & Workshops" description="Register for university webinars, education fairs, visa workshops and overseas study seminars."/><section className="section"><div className="container"><CollectionExplorer items={items} noun="events" searchPlaceholder="Search events, locations, or topics…" filters={[{key: "type", label: "Event type"}, {key: "location", label: "Location"}]} sorts={[{value: "upcoming", key: "starts", label: "Date: soonest"}, {value: "latest", key: "starts", label: "Date: latest", direction: "desc"}, {value: "title", key: "title", label: "Title A–Z"}]} empty={<div className="card"><h3>No events available</h3><p className="muted">Published education fairs and webinars will appear here.</p></div>}/></div></section></PublicShell>;
}
