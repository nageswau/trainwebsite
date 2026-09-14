// Pure, server-renderable SVG charts -- no client JS needed for a static bar chart or
// progress ring. Every number here comes straight from the caller's real report data
// (DATA_MODEL.md §8: no fabricated placeholder figures), so an honestly-empty school
// renders honestly-empty charts, not invented sample data.

export function GradeBarChart({ data }: { data: { grade: string; count: number }[] }) {
  if (data.length === 0) return <p className="muted">No students on the roster yet.</p>;
  const max = Math.max(1, ...data.map((d) => d.count));
  return (
    <div className="grade-bar-chart">
      {data.map((d) => (
        <div className="grade-bar-col" key={d.grade}>
          <span className="grade-bar-count">{d.count}</span>
          <div className="grade-bar-track">
            <div className="grade-bar-fill" style={{ height: `${Math.max(6, (d.count / max) * 100)}%` }} />
          </div>
          <span className="grade-bar-label">{d.grade}</span>
        </div>
      ))}
    </div>
  );
}

export function CompletionRing({ label, value, total, color }: { label: string; value: number; total: number; color: string }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const dash = (pct / 100) * circumference;
  return (
    <div className="report-ring">
      <svg width="128" height="128" viewBox="0 0 128 128" role="img" aria-label={`${label}: ${value} of ${total} students, ${pct}%`}>
        <circle cx="64" cy="64" r={radius} fill="none" stroke="#e7edf6" strokeWidth="12" />
        {total > 0 && (
          <circle
            cx="64" cy="64" r={radius} fill="none" stroke={color} strokeWidth="12" strokeLinecap="round"
            strokeDasharray={`${dash} ${circumference - dash}`} transform="rotate(-90 64 64)"
          />
        )}
        <text x="64" y="60" textAnchor="middle" fontSize="22" fontWeight="800" fill="#0b1f3a">{pct}%</text>
        <text x="64" y="79" textAnchor="middle" fontSize="11" fill="#61728a">{value}/{total}</text>
      </svg>
      <span className="report-ring-label">{label}</span>
    </div>
  );
}
