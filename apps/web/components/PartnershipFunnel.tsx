import { countText, type PerformanceCounts, type PerformanceStep } from "@/lib/partnershipPerformance";

// upc-018 (§17): the student opportunity funnel, data only (it renders on the server). AGN-019's funnel styles: label and count as text, a
// decorative bar below, sized against the largest tracked step. A step the CRM does not track reads "Not tracked", never 0 (U8).
export default function PartnershipFunnel({ steps, counts, label }: { steps: PerformanceStep[]; counts: PerformanceCounts; label: string }) {
  const largest = Math.max(1, ...steps.map((s) => counts[s.key] ?? 0));
  return (
    <ol className="funnel" aria-label={label}>
      {steps.map((s) => {
        const count = counts[s.key];
        return (
          <li className="funnel-row" key={s.key}>
            <span className="funnel-label">{s.label}</span>
            {count === null ? (
              <span className="funnel-count funnel-untracked">{countText(count)}</span> // QA18-01: no bar -- nothing was measured
            ) : (
              <>
                <span className="funnel-count">{countText(count)}</span>
                <span className="funnel-track" aria-hidden="true">
                  {count > 0 && <span className="funnel-fill" style={{ width: `${Math.max(2, Math.round((count * 100) / largest))}%` }} />}
                </span>
              </>
            )}
          </li>
        );
      })}
    </ol>
  );
}
