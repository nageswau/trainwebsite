// ENH-018: shown while the server reads the first page, so navigation is never a blank screen (ENH-011 pattern).
export default function Loading() {
  return (
    <div className="portal-content" aria-busy="true" aria-label="Loading activity feedback">
      <div className="card">
        {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton-line" style={{ width: "100%", marginBottom: 12 }} aria-hidden="true" />)}
      </div>
    </div>
  );
}
