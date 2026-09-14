import Link from "next/link";
import DataTable from "./DataTable";
import type {PortalPayload} from "@/lib/types";

export default function PortalSection({data}: {data: PortalPayload}) {
  return <div className="portal-content">
    <div className="portal-title">
      <div><div className="eyebrow">Workspace</div><h2>{data.title}</h2><p className="muted">{data.subtitle}</p></div>
      <div className="actions">{data.actions.map(action => <Link key={action.label} className="btn small" href={action.href || "#"}>{action.label}</Link>)}</div>
    </div>
    {data.metrics.length > 0 && <div className="metric-grid">{data.metrics.map(metric => <div className="metric" key={metric.label}><span>{metric.label}</span><strong>{metric.value}</strong></div>)}</div>}
    <div className="workspace">
      <div className="workspace-head"><strong>{data.title}</strong><span className="badge">{data.rows.length} role-scoped records</span></div>
      {data.rows.length > 0 && data.columns.length > 0 ? <DataTable key={data.title} columns={data.columns} rows={data.rows} label={data.title}/> : <div className="empty"><h3>No records yet</h3><p>When this workflow has data, permitted records will appear here. Use the relevant action above to begin.</p></div>}
    </div>
    {data.panels?.length > 0 && <div className="panel-list">{data.panels.map(panel => <div className="panel" key={panel.title}><h3>{panel.title}</h3><ul>{panel.items.map(item => <li key={item}>{item}</li>)}</ul></div>)}</div>}
  </div>;
}
