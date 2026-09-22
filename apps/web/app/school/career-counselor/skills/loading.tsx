// ENH-011 (D12): shown while the server reads the skills pages, so navigation is never a blank screen.
export default function Loading() {
  return (
    <div className="portal-content" aria-busy="true" aria-label="Loading skills">
      <div className="card">
        {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton-line" style={{ width: "100%", marginBottom: 12 }} aria-hidden="true" />)}
      </div>
    </div>
  );
}
