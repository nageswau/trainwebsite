import { useEffect, useState } from "react";

import { nowIstInput } from "@/lib/bdmAppointments";

// bdm-006: the `min` for a future-only datetime-local input, read after mount -- a server-rendered value can differ from the browser's
// across a minute boundary (hydration warning). Undefined on the first render; the API still enforces "future only".
export function useNowIstMin(): string | undefined {
  const [min, setMin] = useState<string | undefined>(undefined);
  useEffect(() => setMin(nowIstInput()), []);
  return min;
}
