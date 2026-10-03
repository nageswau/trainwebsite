import { describe, expect, it } from "vitest";

import { currentStep, isJourney, journeyUrl, KIND_LABELS, kindLabel, STATE_LABELS, STEP_LABELS, timelineUrl } from "@/lib/agentJourney";

describe("agentJourney (AGN-015)", () => {
  it("builds the two URLs", () => {
    expect(journeyUrl("s1")).toBe("/api/v1/workflows/overseas/agent/crm/students/s1/journey");
    expect(timelineUrl("s1", 20, 40)).toBe("/api/v1/workflows/overseas/agent/crm/students/s1/timeline?limit=20&offset=40");
  });

  it("labels all nine steps in journey order and every state", () => {
    expect(Object.keys(STEP_LABELS)).toEqual(["create", "counseling", "shortlist", "documents", "application", "offer", "deposit", "visa", "enrollment"]);
    expect(Object.keys(STATE_LABELS).sort()).toEqual(["done", "in_progress", "not_required", "not_started", "refunded", "refused", "withdrawn"]);
    expect(STATE_LABELS.not_required).toBe("Not required");
  });

  it("labels every kind the server sends and humanises unknown ones", () => {
    const server = [
      "student_created", "student_updated", "student_duplicate_override", "student_assigned", "student_archived", "student_restored",
      "counseling_saved", "shortlist_added", "shortlist_updated", "shortlist_removed", "task_added", "task_updated", "task_completed",
      "task_cancelled", "application_created", "application_stage_changed", "application_withdrawn", "application_enrolled",
      "application_updated", "application_edited", "enrollment_updated", "visa_started", "visa_updated", "visa_stage_changed",
      "visa_decision_recorded", "deposit_set", "deposit_paid", "deposit_remitted", "deposit_refunded", "document_uploaded",
      "document_replaced", "document_verified", "document_rejected", "document_changes_required", "document_requested",
      "document_fulfilled", "document_request_cancelled", "document_downloaded",
    ];
    expect(server.filter((k) => !(k in KIND_LABELS))).toEqual([]);
    expect(kindLabel("application_stage_changed")).toBe("Application stage changed");
    expect(kindLabel("brand_new_kind")).toBe("Brand new kind");
  });

  it("guards the journey shape", () => {
    expect(isJourney({ student: { id: "s1" }, steps: [], applications: [] })).toBe(true);
    expect(isJourney({ items: [], total: 0 })).toBe(false);
    expect(isJourney(null)).toBe(false);
  });

  it("finds the first unsettled step", () => {
    expect(currentStep([{ key: "create", state: "done" }, { key: "counseling", state: "in_progress" }])).toBe("counseling");
    expect(currentStep([{ key: "deposit", state: "not_required" }, { key: "visa", state: "not_started" }])).toBe("visa");
    expect(currentStep([{ key: "create", state: "done" }])).toBeNull();
  });
});
