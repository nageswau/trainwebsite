import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import LedgerCategories from "@/components/LedgerCategories";
import LedgerShell from "@/components/LedgerShell";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe } from "@/lib/management";
import { LEDGER_API, LEDGER_HOME, type LedgerCategory } from "@/lib/managementLedger";

// mgmt-004 (ML1-ML3): the managed category list, seeded from EVID-017 §8 (expenses) and §22 (income).
export default async function LedgerCategoriesPage() {
  let me: ManagementMe;
  let categories: LedgerCategory[];
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
    categories = (await serverApi<{ items: LedgerCategory[] }>(`${LEDGER_API}/categories`)).items;
  } catch (e) {
    if (e instanceof ApiError && e.status >= 500) throw e;
    return accessUnavailable(e, "/admin/login");
  }
  return (
    <LedgerShell me={me} title="Ledger categories" actions={<Link className="btn secondary" href={LEDGER_HOME}>Back to the ledger</Link>}
      intro="Deactivating a category keeps its entries and figures; it is only left out when recording new entries.">
      <LedgerCategories categories={categories} />
    </LedgerShell>
  );
}
