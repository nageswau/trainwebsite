import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import OverlapNotice from "@/components/OverlapNotice";
import PartnershipCalendar from "@/components/PartnershipCalendar";
import type { CalendarItem, Overlap, PartnershipCalendarData } from "@/lib/partnershipCalendar";

// upc-011 (§9, CL1, CL10, CL13; AC1, AC2): the read-only calendar and the overlap notice.
afterEach(cleanup);
const asha = { id: "u1", full_name: "Asha Rao", active: true };
const item = (over: Partial<CalendarItem>): CalendarItem => ({
  source: "event", id: "e1", code: "PEV-000001", title: "QS Fair", kind: "education_fair", starts_on: "2031-03-04", ends_on: "2031-03-06",
  starts_at: null, status: "scheduled", university: null, people: [asha], overlaps: [], ...over,
});
const fair = item({});
const visit = item({ source: "visit", id: "v1", code: "VIS-000003", title: "Oxford, Oxford", kind: "university_visit", starts_on: "2031-03-05", ends_on: "2031-03-05", status: "approved" });
const meeting = item({ source: "meeting", id: "m1", code: "UMT-000002", title: "Oxford", kind: "university_meeting", starts_on: "2031-03-03", ends_on: "2031-03-03", starts_at: "2031-03-03T04:30:00Z" });
const overlap = (target: CalendarItem): Overlap => ({ employee: asha, item: { source: target.source, id: target.id, code: target.code, title: target.title } });
const data = (items: CalendarItem[]): PartnershipCalendarData => ({ date_from: "2031-03-03", date_to: "2031-03-09", today: "2031-03-04", employee: asha, truncated: false, items });

describe("PartnershipCalendar", () => {
  it("lists every day of the week, a multi-day event on each of its days, with kinds, times and links (AC1)", () => {
    render(<PartnershipCalendar data={data([meeting, fair, visit])} view="week" date="2031-03-05" />);
    expect(screen.getAllByRole("heading", { level: 4 })).toHaveLength(7);
    const monday = screen.getByRole("region", { name: /Monday 3 Mar/ });
    expect(within(monday).getByText("University meeting")).toBeInTheDocument();
    expect(within(monday).getByText("10:00 IST")).toBeInTheDocument();
    expect(within(monday).getByRole("link", { name: "UMT-000002 — Oxford" })).toHaveAttribute("href", "/partnership/meetings/m1");
    for (const day of [/Tuesday 4 Mar/, /Wednesday 5 Mar/, /Thursday 6 Mar/]) {
      expect(within(screen.getByRole("region", { name: day })).getByRole("link", { name: "PEV-000001 — QS Fair" })).toHaveAttribute("href", "/partnership/events/e1");
    }
    expect(within(screen.getByRole("region", { name: /Wednesday 5 Mar/ })).getByText("Approved")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /Sunday 9 Mar/ })).toHaveTextContent("Nothing planned");
    expect(screen.getByRole("link", { name: "Month" })).toHaveAttribute("href", "/partnership/calendar?view=month&date=2031-03-05");
    expect(screen.getByRole("link", { name: "Next week" })).toHaveAttribute("href", "/partnership/calendar?view=week&date=2031-03-12");
  });

  it("flags overlapping items and summarises them (AC2)", () => {
    render(<PartnershipCalendar data={data([item({ overlaps: [overlap(visit)] }), item({ ...visit, overlaps: [overlap(fair)] })])} view="week" date="2031-03-05" />);
    expect(screen.getByRole("note")).toHaveTextContent("2 items overlap");
    const wednesday = screen.getByRole("region", { name: /Wednesday 5 Mar/ });
    const markers = within(wednesday).getAllByText(/^Overlap — Asha Rao:/);
    expect(markers).toHaveLength(2);
    // QA-02: one short line per person; each overlapping item is a link by its code (its title on hover), the name not repeated.
    expect(within(markers[0]).getByRole("link", { name: "VIS-000003" })).toHaveAttribute("href", "/partnership/visits/v1");
    expect(within(markers[0]).getByRole("link", { name: "VIS-000003" })).toHaveAttribute("title", "Oxford, Oxford");
  });

  it("lists one line per person with several overlaps (QA-02)", () => {
    const ben = { id: "u2", full_name: "Ben Ito", active: true };
    const busy = item({ overlaps: [overlap(visit), overlap(meeting), { employee: ben, item: overlap(visit).item }] });
    render(<PartnershipCalendar data={data([busy])} view="week" date="2031-03-05" />);
    const tuesday = screen.getByRole("region", { name: /Tuesday 4 Mar/ });
    expect(within(tuesday).getByText(/^Overlap — Asha Rao:/)).toHaveTextContent("Overlap — Asha Rao: VIS-000003, UMT-000002");
    expect(within(tuesday).getByText(/^Overlap — Ben Ito:/)).toHaveTextContent("Overlap — Ben Ito: VIS-000003");
  });

  it("shows only days with items in the month view, keeping the employee in links", () => {
    render(<PartnershipCalendar data={data([visit])} view="month" date="2031-03-05" employee="u1" />);
    expect(screen.getAllByRole("heading", { level: 4 })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Previous month" })).toHaveAttribute("href", "/partnership/calendar?view=month&date=2031-02-01&employee=u1");
  });

  it("has empty and error states", () => {
    const { unmount } = render(<PartnershipCalendar data={data([])} view="month" date="2031-03-05" />);
    expect(screen.getByRole("status")).toHaveTextContent("Nothing planned this month.");
    unmount();
    render(<PartnershipCalendar data={null} view="week" date="2031-03-05" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Unable to load the calendar.");
    expect(screen.getByRole("link", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("OverlapNotice", () => {
  it("links each overlap and renders nothing without one", () => {
    const { container, rerender } = render(<OverlapNotice overlaps={[]} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<OverlapNotice overlaps={[overlap(visit)]} />);
    expect(screen.getByRole("note")).toHaveTextContent("Overlaps with other plans");
    expect(screen.getByRole("link", { name: "Asha Rao is also at VIS-000003 (Oxford, Oxford)" })).toHaveAttribute("href", "/partnership/visits/v1");
  });
});
