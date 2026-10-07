import { describe, expect, it } from "vitest";

import {
  CALL_TYPES, OUTCOMES, closesAs, formatDuration, isLeadCall, isLogCallResult, leadCallsUrl, needsFollowUp, outcomeLabel, toSeconds,
} from "@/lib/telecallerCalls";
import { call } from "@/tests/helpers/calls";

// tel-010 (DEC-SCOPE-096): the outcome catalogue and helpers mirror the API's (services/lead_calls.py).
describe("telecallerCalls (tel-010)", () => {
  it("offers the 13 EVID-019 §5 outcomes and never Converted (T5)", () => {
    expect(OUTCOMES).toHaveLength(13);
    expect(OUTCOMES.map((o) => o.key)).not.toContain("converted");
    expect(outcomeLabel("interested")).toBe("Connected – Interested");
    expect(outcomeLabel("unknown_key")).toBe("unknown_key");
    expect(CALL_TYPES.map((t) => t.key)).toEqual(["outgoing", "incoming"]); // CL1
  });

  it("knows which outcomes close the lead and which need a follow-up (D3, D4)", () => {
    expect(closesAs("already_joined")).toBe("Lost");
    expect(closesAs("wrong_number")).toBe("Wrong Number");
    expect(closesAs("busy")).toBeNull();
    expect(needsFollowUp("call_back_requested")).toBe(true);
    expect(needsFollowUp("follow_up_required")).toBe(true);
    expect(needsFollowUp("interested")).toBe(false);
  });

  it("formats and parses durations", () => {
    expect(formatDuration(0)).toBe("0 s");
    expect(formatDuration(45)).toBe("45 s");
    expect(formatDuration(245)).toBe("4 min 5 s");
    expect(formatDuration(600)).toBe("10 min");
    expect(toSeconds("4", "5")).toBe(245);
    expect(toSeconds("", "")).toBe(0);
    expect(toSeconds("1.5", "0")).toBeNull();
    expect(toSeconds("0", "60")).toBeNull();
    expect(toSeconds("-1", "0")).toBeNull();
  });

  it("builds URLs and guards bodies", () => {
    expect(leadCallsUrl("L 1")).toBe("/api/v1/telecaller/leads/L%201/calls?limit=50");
    expect(isLeadCall(call())).toBe(true);
    expect(isLeadCall({ id: "x" })).toBe(false);
    expect(isLogCallResult({ call: call(), lead: { id: "L1", status: "contacted", status_label: "Contacted" }, follow_up_id: null })).toBe(true);
    expect(isLogCallResult({ call: call() })).toBe(false);
  });
});
