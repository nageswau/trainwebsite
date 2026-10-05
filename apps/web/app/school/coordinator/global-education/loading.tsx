// ENH-017: shown while the server reads the pipeline, so navigation is never a blank screen (ENH-018 pattern).
export default function Loading() {
  return (
    <div className="portal-content" aria-busy="true" aria-label="Loading global education pipeline">
      <div className="card">
        {[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="skeleton-line" style={{ width: "100%", marginBottom: 12 }} aria-hidden="true" />)}
      </div>
    </div>
  );
}
