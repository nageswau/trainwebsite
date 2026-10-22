// ccrm-002 (DEC-SCOPE-242, API §12EU): append-only lead notes. Each lead route serves `/notes` in its own scope; the API decides who writes.
import type { TimelineEntry } from "@/lib/leadTimeline";
import type { PersonRef } from "@/lib/telecallerLeads";

export type LeadNote = { id: string; at: string; author: PersonRef; body: string };

export const NOTE_MAX = 4000;

/** A note as a `LeadTimeline` row: no title (QA-01: every row is a note), author and time, then the whole text (the activity timeline
 *  shows an excerpt). */
export const noteEntry = (note: LeadNote): TimelineEntry => ({ badge: "", tone: "var(--navy)", title: "", meta: [], when: null, detail: note.body });
export const noteAuthor = (note: LeadNote) => note.author.full_name;
