// ENH-011 (D12): shown while the server reads the batch, so opening one is never a blank screen.
export default function Loading() {
  return (
    <div className="portal-content" aria-busy="true" aria-label="Loading batch" style={{ display: "grid", gap: 20 }}>
      {[0, 1, 2].map((card) => (
        <div key={card} className="card">
          {[0, 1].map((i) => <div key={i} className="skeleton-line" style={{ width: "100%", marginBottom: 12 }} aria-hidden="true" />)}
        </div>
      ))}
    </div>
  );
}
