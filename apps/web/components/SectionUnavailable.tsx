// ENH-016: one section of a dashboard failed to load -- the rest of the page still renders (spec §8 error state).
export default function SectionUnavailable({ title }: { title: string }) {
  return (
    <div className="card">
      <h2>{title}</h2>
      <p className="muted" role="status">This section couldn&apos;t load. Refresh to try again.</p>
    </div>
  );
}
