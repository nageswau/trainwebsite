import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import LocalTime from "@/components/LocalTime";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { fileSize } from "@/lib/recruiterCandidates";
import { PAGE_SIZE, pageOffset } from "@/lib/telecaller";
import type { User } from "@/lib/types";
import { shellFor, universityPath } from "@/lib/universities";
import {
  DOCUMENT_KINDS,
  type DocumentFilters,
  documentFileUrl,
  documentListQuery,
  documentPageHref,
  DOCUMENTS_PATH,
  DOCUMENTS_URL,
  kindLabel,
  type UniversityDocument,
} from "@/lib/universityDocuments";

// upc-026 (DC12): the §32 "Documents" menu -- every document the reader may see, across universities, newest change first. Filters and
// paging live in the URL; a plain GET form, so it works without JavaScript. Uploads happen on each university's page (its Documents
// section). The API is the gate and the slice: any other role gets its 403 here with a link home.
export default async function DocumentsPage({ searchParams }: { searchParams: Promise<DocumentFilters> }) {
  const filters = await searchParams;
  const offset = pageOffset(filters.offset);
  let user: User, page: Page<UniversityDocument>;
  try {
    [user, page] = await Promise.all([serverApi<User>("/api/v1/auth/me"), serverApi<Page<UniversityDocument>>(`${DOCUMENTS_URL}?${documentListQuery(filters, PAGE_SIZE, offset)}`)]);
  } catch (e) {
    return accessUnavailable(e, "/overseas/login");
  }
  const { nav, roleLabel } = shellFor(user.role);
  const filtered = Boolean(filters.kind || filters.q?.trim());
  const end = page.offset + page.items.length;
  return (
    <PortalShell nav={nav} roleLabel={roleLabel} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Documents</div>
            <h2>University documents</h2>
            <p className="muted">Agreements, brochures, course lists, fee structures and every other university document in one place. Upload them from each university&apos;s page.</p>
          </div>
        </div>
        <form method="get" action={DOCUMENTS_PATH} className="card" aria-label="Filter documents" style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "end", padding: 14, marginBottom: 16 }}>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="doc-filter-kind">Kind</label>
            <select id="doc-filter-kind" name="kind" defaultValue={filters.kind ?? ""}>
              <option value="">Any kind</option>
              {Object.entries(DOCUMENT_KINDS).map(([key, word]) => <option key={key} value={key}>{word}</option>)}
            </select>
          </div>
          <div className="field" style={{ margin: 0, flex: "1 1 14rem" }}>
            <label htmlFor="doc-filter-q">Search</label>
            <input id="doc-filter-q" name="q" type="search" maxLength={100} defaultValue={filters.q ?? ""} placeholder="Title, university or code" />
          </div>
          <button type="submit" className="btn secondary small">Apply</button>
          {filtered && <Link className="btn ghost small" href={DOCUMENTS_PATH}>Clear</Link>}
        </form>
        {page.total === 0 ? (
          <p className="empty" role="status">{filtered ? "No documents match these filters." : "No documents uploaded yet."}</p>
        ) : page.items.length === 0 ? (
          <>
            <p className="empty" role="status">This page is past the end of the list.</p>
            <Link className="btn secondary small" href={documentPageHref(filters, 0)}>Go to the first page</Link>
          </>
        ) : (
          <div className="telecaller-list">
            <div className="table-wrap" role="region" aria-label="University documents" tabIndex={0}>
              <table>
                <caption className="visually-hidden">University documents, {page.total} in total</caption>
                <thead>
                  <tr>
                    <th scope="col">Document</th><th scope="col">Kind</th><th scope="col">University</th><th scope="col">Version</th>
                    <th scope="col">Sharing</th><th scope="col">Last upload</th><th scope="col">File</th>
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((d) => {
                    const current = d.versions[0];
                    return (
                      <tr key={d.id}>
                        <td data-label="Document" style={{ overflowWrap: "anywhere" }}>{d.title}</td>
                        <td data-label="Kind">{kindLabel(d.kind)}</td>
                        {/* QA-01: one wrapper per mixed cell -- on a phone each cell is a flex row, which would split the parts into columns */}
                        <td data-label="University">
                          <span><Link href={universityPath(d.university.id)}>{d.university.name}</Link> <span className="muted" style={{ whiteSpace: "nowrap" }}>{d.university.university_code}</span></span>
                        </td>
                        <td data-label="Version">{d.current_version}</td>
                        <td data-label="Sharing"><span className="badge">{d.shareable ? "Shareable" : "Internal"}</span></td>
                        <td data-label="Last upload"><span>{current ? <>{current.uploaded_by.full_name}, <LocalTime value={current.uploaded_at} /></> : "—"}</span></td>
                        <td data-label="File">
                          <span>
                            <a href={documentFileUrl(d)} download>Download<span className="visually-hidden"> {d.title}</span></a>
                            {current && <span className="muted"> · {fileSize(current.size_bytes)}</span>}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {page.total > page.limit && (
              <nav aria-label="Document pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
                <span className="muted" style={{ fontSize: 13 }}>Showing {page.offset + 1}–{end} of {page.total}</span>
                {page.offset > 0 && <Link className="btn secondary small" aria-label="Previous page" href={documentPageHref(filters, Math.max(0, page.offset - page.limit))}>Previous</Link>}
                {end < page.total && <Link className="btn secondary small" aria-label="Next page" href={documentPageHref(filters, end)}>Next</Link>}
              </nav>
            )}
          </div>
        )}
      </div>
    </PortalShell>
  );
}
