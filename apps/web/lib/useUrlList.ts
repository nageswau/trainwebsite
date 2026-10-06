"use client";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import type { Page } from "@/lib/apiErrors";
import { pageOffset } from "@/lib/telecaller";
import { CATALOGUE_PAGE_SIZE, getPage } from "@/lib/telecallerCatalogue";

// tel-012: one paged list whose single filter and page live in the URL (?<filterKey>=&offset=), so refresh keeps the place and Back
// returns to the previous view (the tel-002 QA-04 behaviour, shared by the three library screens). `allowed` drops an unknown value.
export function useUrlList<T>(url: string, filterKey: string, allowed?: readonly string[]) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const raw = params.get(filterKey) ?? "";
  const filter = !allowed || allowed.includes(raw) ? raw : "";
  const offset = pageOffset(params.get("offset") ?? undefined);
  const [data, setData] = useState<Page<T> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoadFailed(false);
    const query = new URLSearchParams({ limit: String(CATALOGUE_PAGE_SIZE), offset: String(offset) });
    if (filter) query.set(filterKey, filter);
    getPage<T>(`${url}?${query}`, controller.signal).then(setData).catch(() => controller.signal.aborted || setLoadFailed(true));
    return () => controller.abort();
  }, [url, filterKey, filter, offset, version]);

  function go(nextFilter: string, nextOffset: number) {
    const next = new URLSearchParams();
    if (nextFilter) next.set(filterKey, nextFilter);
    if (nextOffset > 0) next.set("offset", String(nextOffset));
    router.push(next.size ? `${pathname}?${next}` : pathname, { scroll: false });
  }

  return { data, loadFailed, reload: () => setVersion((v) => v + 1), filter, offset, go };
}

export type UrlList<T> = ReturnType<typeof useUrlList<T>>;
