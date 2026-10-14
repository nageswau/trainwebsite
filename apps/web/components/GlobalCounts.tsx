import CountryFlag from "@/components/CountryFlag";
import Link from "next/link";

export type CountRow = { key: string; label: string; count: number; href?: string; iso2?: string | null };  // iso2: PUB-023 flag (country rows only)

// upc-029 (§31 sub-views): one captioned "label → count" table inside a dashboard column. Data only, so the server page can render it.
export default function GlobalCounts({ caption, rows }: { caption: string; rows: CountRow[] }) {
  return (
    <table className="global-counts">
      <caption>{caption}</caption>
      <tbody>
        {rows.length === 0 ? (
          <tr><td className="muted" colSpan={2}>None</td></tr>
        ) : (
          rows.map((r) => (
            <tr key={r.key}>
              <th scope="row"><CountryFlag iso2={r.iso2} />{r.href ? <Link href={r.href}>{r.label}</Link> : r.label}</th>
              <td>{r.count.toLocaleString("en-IN")}</td>
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}
