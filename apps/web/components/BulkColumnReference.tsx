import type { BulkColumn } from "@/lib/bulkEntry";

// The collapsible "Column reference" table shared by the bulk-upload panels (ENH-028 bulk entry, ENH-029 school onboarding).
export default function BulkColumnReference({ columns }: { columns: BulkColumn[] }) {
  return (
    <details style={{ marginTop: 12 }}>
      <summary>Column reference</summary>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr><th>Column</th><th>Required</th><th>Format</th><th>Example</th></tr>
          </thead>
          <tbody>
            {columns.map((c) => (
              <tr key={c.name}>
                <td data-label="Column"><code>{c.name}</code></td>
                <td data-label="Required">{c.required ? "Yes" : "No"}</td>
                <td data-label="Format">{c.format}</td>
                <td data-label="Example">{c.example}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
