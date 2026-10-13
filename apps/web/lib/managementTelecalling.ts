import { isCalendarDate } from "@/lib/formatDate";

// mgmt-019 (EVID-017 §14, spec TC1-TC16): GET /management/telecalling -- the eight §14 figures and telecaller conversion for the company,
// each team and each telecaller over a period (default this month to date), and the Calls → Interested → Counseling → Registration
// chain. The API decides access (operational tier), the period rules and every count; the page holds the dates in the address.
export const TELECALLING_HOME = "/management/telecalling";
const TELECALLING_API = "/api/v1/management/telecalling";

export type TelecallingFigures = {
  leads: number; calls: number; connected: number; interested: number; follow_ups: number; appointments: number; converted: number;
  lost: number; counselling: number; conversion: number | null;
}; // prettier-ignore
export type TelecallingTeam = TelecallingFigures & { team: string; label: string; telecallers: number };
export type TelecallingRow = TelecallingFigures & { user_id: string; full_name: string; team: string; active: boolean };
export type TelecallingStep = { key: string; label: string; value: number; share: number | null };
export type Telecalling = {
  date_from: string; date_to: string; totals: TelecallingFigures; teams: TelecallingTeam[]; telecallers: TelecallingRow[]; chain: TelecallingStep[];
}; // prettier-ignore

// The source's eight figures (§14), in its order and words.
export const TELECALLING_FIGURES: { key: keyof TelecallingFigures; label: string }[] = [
  { key: "leads", label: "Leads assigned" }, { key: "calls", label: "Calls attempted" }, { key: "connected", label: "Connected" },
  { key: "interested", label: "Interested" }, { key: "follow_ups", label: "Follow-up" }, { key: "appointments", label: "Appointment" },
  { key: "converted", label: "Converted" }, { key: "lost", label: "Lost" },
]; // prettier-ignore

export type TelecallingFilters = { date_from: string; date_to: string };

/** The dates from the page's search params; a repeated or impossible date only comes from a hand-edited address and is dropped. */
export function telecallingFilters(search: Record<string, string | string[] | undefined>): TelecallingFilters {
  const day = (key: string) => {
    const value = search[key];
    return typeof value === "string" && isCalendarDate(value) ? value : "";
  };
  return { date_from: day("date_from"), date_to: day("date_to") };
}

function withQuery(path: string, filters: TelecallingFilters): string {
  const query = new URLSearchParams();
  if (filters.date_from) query.set("date_from", filters.date_from);
  if (filters.date_to) query.set("date_to", filters.date_to);
  const text = query.toString();
  return text ? `${path}?${text}` : path;
}

export const telecallingUrl = (filters: TelecallingFilters) => withQuery(TELECALLING_API, filters);
export const telecallingHref = (filters: TelecallingFilters) => withQuery(TELECALLING_HOME, filters);

/** TC10: "12.5%", or a dash when no lead was assigned. */
export const conversionText = (conversion: number | null) => (conversion === null ? "—" : `${conversion}%`);

/** TC11 (QA19-03): a later chain step's share of the calls, or null (Calls itself, or no calls in the period). */
export const stepShareText = (share: number | null) => (share === null ? null : `${share}% of calls`);
