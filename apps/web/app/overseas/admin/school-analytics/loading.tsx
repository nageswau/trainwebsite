// ENH-016: shown while the server reads every school's figures, so navigation is never a blank screen (ENH-018 pattern).
export default function Loading() {
  return (
    <div className="portal-content" aria-busy="true" aria-label="Loading school analytics">
      <div className="card">
        {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton-line" style={{ width: "100%", marginBottom: 12 }} aria-hidden="true" />)}
      </div>
    </div>
  );
}
