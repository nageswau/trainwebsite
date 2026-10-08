// upc-007 (DEC-SCOPE-121): the partnership stage engine and Kanban board. The API owns the catalogue (labels and columns come with every
// university) and every rule; these helpers only shape requests and read responses.
import type { ManagerRef } from "@/lib/telecaller";
import { UNIVERSITIES_URL } from "@/lib/universities";

export type StageRef = { key: string; label: string; column: string };
export type UniversityPipeline = {
  stage: string; stage_label: string; column: string; column_label: string; changed_at: string; lost: { at: string; reason: string } | null;
  stages: StageRef[];
};
export type BoardColumn = { key: string; label: string; stages: string[]; count: number };
export type BoardItem = {
  id: string; university_code: string; name: string; city: string; country_name: string; stage: string; stage_label: string; column: string;
  lost: boolean; primary_manager: ManagerRef | null;
};
export type Board = { columns: BoardColumn[]; lost_count: number; items: BoardItem[]; total: number; limit: number; offset: number };
export type BoardChange = { column?: string | null; offset?: number };

export const PIPELINE_URL = "/api/v1/partnership/pipeline";
export const PIPELINE_PATH = "/partnership/pipeline";
export const LOST = "lost";
export const BOARD_PAGE = 50;
const HISTORY_PAGE = 20;

export const stageHistoryUrl = (id: string, offset = 0) => `${UNIVERSITIES_URL}/${id}/stage-history?limit=${HISTORY_PAGE}&offset=${offset}`;

/** PS4: moving to an earlier stage needs a note. */
export function isBackward(p: Pick<UniversityPipeline, "stage" | "stages">, to: string): boolean {
  const keys = p.stages.map((s) => s.key);
  return keys.indexOf(to) < keys.indexOf(p.stage);
}

/** The 409 for a Lost flag someone else changed (`university_lost` / `university_not_lost`): its message, else null. */
export function lostConflict(detail: unknown): string | null {
  const d = detail as { code?: unknown; message?: unknown } | null;
  const lost = d && typeof d === "object" && (d.code === "university_lost" || d.code === "university_not_lost");
  return lost && typeof d.message === "string" ? d.message : null;
}

export function boardQuery({ mine, column, offset = 0 }: { mine: boolean; column?: string; offset?: number }): string {
  const q = new URLSearchParams();
  if (mine) q.set("manager", "me");
  if (column) q.set("column", column);
  q.set("limit", String(BOARD_PAGE));
  q.set("offset", String(offset));
  return q.toString();
}

/** The page's own address: `scope=all` (managers' toggle), the chosen column and the offset. */
export function boardHref({ all, column, offset = 0 }: { all: boolean; column?: string | null; offset?: number }): string {
  const q = new URLSearchParams();
  if (all) q.set("scope", "all");
  if (column) q.set("column", column);
  if (offset > 0) q.set("offset", String(offset));
  const query = q.toString();
  return query ? `${PIPELINE_PATH}?${query}` : PIPELINE_PATH;
}
