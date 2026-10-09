import Link from "next/link";

import { itemHref, type Overlap, overlapText } from "@/lib/partnershipCalendar";

// upc-011 (CL10/CL11, AC2): the overlap warning on a meeting, visit or event page -- each employee who is also on another calendar item
// at the same time, linked to that item. A warning only; nothing is blocked. Renders nothing when there is no overlap.
export default function OverlapNotice({ overlaps }: { overlaps: Overlap[] | undefined }) {
  if (!overlaps?.length) return null;
  return (
    <div className="form-warning" role="note" aria-labelledby="overlap-title" style={{ marginBottom: 16 }}>
      <p id="overlap-title" style={{ margin: 0, fontWeight: 700 }}>Overlaps with other plans</p>
      <ul style={{ margin: "4px 0 0", paddingLeft: 20 }}>
        {overlaps.map((o) => (
          <li key={`${o.employee.id}-${o.item.source}-${o.item.id}`} style={{ overflowWrap: "anywhere" }}>
            <Link href={itemHref(o.item)}>{overlapText(o)}</Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
