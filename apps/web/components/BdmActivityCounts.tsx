import { CHANNEL_LABEL, CHANNELS, type DayCounts } from "@/lib/bdmActivities";

// bdm-009 (AC3): the whole day's counts from the API (never summed from the visible page), on AGN-018's KPI tiles (§12.2 F1:
// one column on phones, two from 768 px, four from 1024 px). `busy` marks a re-read in progress; the old numbers stay visible.
export default function BdmActivityCounts({ counts, busy = false }: { counts: DayCounts; busy?: boolean }) {
  const tiles: [string, number][] = [
    ["Calls made", counts.calls_made],
    ["Organizations contacted", counts.organizations_contacted],
    ...CHANNELS.map((c): [string, number] => [CHANNEL_LABEL[c], counts.by_channel[c] ?? 0]),
  ];
  return (
    <dl className="kpi-grid" aria-label="Day counts" aria-busy={busy || undefined}>
      {tiles.map(([label, value]) => (
        <div className="kpi-tile" key={label}>
          <dt>{label}</dt>
          <dd className="kpi-value">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
