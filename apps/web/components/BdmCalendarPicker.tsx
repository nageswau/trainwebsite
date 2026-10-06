"use client";

import { useRouter } from "next/navigation";

import SearchableSelect from "@/components/SearchableSelect";
import { teamMemberSearch } from "@/lib/bdmAppointments";
import { type CalendarView, pageHref } from "@/lib/bdmCalendar";
import type { PickOption } from "@/lib/lookups";

// bdm-013 (K3): the manager's BDM choice for the calendar -- their team (super_admin: everyone). Picking navigates; the page reads the API.
export default function BdmCalendarPicker({ view, date, current }: { view: CalendarView; date: string; current: PickOption | null }) {
  const router = useRouter();
  return (
    <div style={{ maxWidth: 420, marginBottom: 12 }}>
      <SearchableSelect key={current?.id ?? "none"} label="BDM" noun="BDM" search={teamMemberSearch()} initial={current}
        onChange={(o) => router.push(o ? pageHref("/bdm/manager/calendar", { view, date, bdm: o.id }) : "/bdm/manager/calendar")} />
    </div>
  );
}
