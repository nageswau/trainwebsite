import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { pickOption } from "../helpers/pickOption";
import FundingRecordForm from "@/components/FundingRecordForm";
import type { FundingRecord } from "@/lib/fundingRecords";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

const STUDENTS = [{ id: "s1", full_name: "Asha", school_name: "Hill School" }];
const CASE: FundingRecord = {
  id: "f1", school_student_id: "s1", support_type: "education_loan", status: "documents", status_changed_on: "2026-09-20",
  provider_name: "HDFC", amount_text: "₹5 lakh", notes: "Collecting papers", closure_reason: null,
  created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-20T00:00:00Z", counselor_name: "Anita", updated_by_name: null,
};

function respond(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("FundingRecordForm", () => {
  it("creates a case with the student, type and optional details", async () => {
    const fetchMock = respond(201, { id: "f9" });
    const onDone = vi.fn();
    render(<FundingRecordForm students={STUDENTS} onDone={onDone} onCancel={vi.fn()} />);
    pickOption(screen, "Student", "s1");
    fireEvent.change(screen.getByLabelText("Support type"), { target: { value: "scholarship" } });
    fireEvent.change(screen.getByLabelText("Provider or institution (optional)"), { target: { value: "Tata Trust" } });
    fireEvent.change(screen.getByLabelText("Amount (optional)"), { target: { value: "50% tuition" } });
    fireEvent.change(screen.getByLabelText("Notes"), { target: { value: "Needs-based" } });
    fireEvent.click(screen.getByRole("button", { name: "Add case" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Case saved.");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/school/funding-records", expect.objectContaining({ method: "POST" }));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      school_student_id: "s1", support_type: "scholarship", provider_name: "Tata Trust", amount_text: "50% tuition", notes: "Needs-based",
    });
    expect(refresh).toHaveBeenCalled();
    expect(onDone).toHaveBeenCalled();
    expect(screen.getByLabelText("Support type")).toHaveValue("");
  });

  it("offers only the current stage, the next one and Closed when editing", () => {
    render(<FundingRecordForm students={STUDENTS} record={CASE} onDone={vi.fn()} onCancel={vi.fn()} />);
    const options = Array.from((screen.getByLabelText("Stage") as HTMLSelectElement).options).map((o) => o.value);
    expect(options).toEqual(["documents", "application", "closed"]);
    expect(screen.queryByLabelText("Support type")).not.toBeInTheDocument();
  });

  it("asks for a reason only when closing, and moves focus to it", async () => {
    render(<FundingRecordForm students={STUDENTS} record={CASE} onDone={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByLabelText("Reason for closing")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Stage"), { target: { value: "closed" } });
    const reason = screen.getByLabelText("Reason for closing");
    expect(reason).toBeRequired();
    await waitFor(() => expect(reason).toHaveFocus());
  });

  it("sends the stage it was opened at as expected_status and only the edited fields", async () => {
    const fetchMock = respond(200, { ...CASE, status: "application" });
    render(<FundingRecordForm students={STUDENTS} record={CASE} onDone={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Stage"), { target: { value: "application" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByRole("status");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/school/funding-records/f1");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      expected_status: "documents", status: "application", provider_name: "HDFC", amount_text: "₹5 lakh", notes: "Collecting papers",
    });
  });

  it("sends the closure reason only when closing", async () => {
    const fetchMock = respond(200, { ...CASE, status: "closed" });
    render(<FundingRecordForm students={STUDENTS} record={CASE} onDone={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Stage"), { target: { value: "closed" } });
    fireEvent.change(screen.getByLabelText("Reason for closing"), { target: { value: "Bank refused" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByRole("status");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({ status: "closed", closure_reason: "Bank refused" });
  });

  it("offers a reload when someone else changed the case (409)", async () => {
    respond(409, { detail: "This case was changed by someone else (now Application). Reload to see the latest." });
    const onCancel = vi.fn();
    render(<FundingRecordForm students={STUDENTS} record={CASE} onDone={vi.fn()} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("changed by someone else");
    fireEvent.click(screen.getByRole("button", { name: "Discard my changes and reload" }));
    expect(refresh).toHaveBeenCalled();
    expect(onCancel).toHaveBeenCalled();
  });

  it("keeps the entry and explains a server error or a lost connection", async () => {
    respond(500, { detail: "Internal Server Error" });
    render(<FundingRecordForm students={STUDENTS} record={CASE} onDone={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Notes"), { target: { value: "typed text" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side. Please try again; your entry is kept.");
    expect(screen.getByLabelText("Notes")).toHaveValue("typed text");
    cleanup();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    render(<FundingRecordForm students={STUDENTS} record={CASE} onDone={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The request did not complete");
  });

  it("shows the server's own words for a refusal (tier, duplicate case)", async () => {
    respond(409, { detail: "Asha already has an open scholarship case. Open it from the list to update it." });
    render(<FundingRecordForm students={STUDENTS} onDone={vi.fn()} onCancel={vi.fn()} />);
    pickOption(screen, "Student", "s1");
    fireEvent.change(screen.getByLabelText("Support type"), { target: { value: "scholarship" } });
    fireEvent.click(screen.getByRole("button", { name: "Add case" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Asha already has an open scholarship case.");
    expect(screen.queryByRole("button", { name: "Discard my changes and reload" })).not.toBeInTheDocument();
  });

  it("disables the form and marks the button busy while saving", async () => {
    let resolve: (value: unknown) => void = () => undefined;
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise((r) => { resolve = r; })));
    render(<FundingRecordForm students={STUDENTS} record={CASE} onDone={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    const button = await screen.findByRole("button", { name: "Saving…" });
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(screen.getByLabelText("Notes")).toBeDisabled();
    resolve({ ok: true, status: 200, json: async () => CASE });
    await screen.findByRole("status");
  });

  it("caps text at the server's limits", () => {
    render(<FundingRecordForm students={STUDENTS} record={CASE} onDone={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Stage"), { target: { value: "closed" } });
    expect(screen.getByLabelText("Provider or institution (optional)")).toHaveAttribute("maxLength", "200");
    expect(screen.getByLabelText("Amount (optional)")).toHaveAttribute("maxLength", "120");
    expect(screen.getByLabelText("Reason for closing")).toHaveAttribute("maxLength", "500");
    expect(screen.getByLabelText("Notes")).toHaveAttribute("maxLength", "4000");
  });

  it("cancels an edit with Escape", () => {
    const onCancel = vi.fn();
    render(<FundingRecordForm students={STUDENTS} record={CASE} onDone={vi.fn()} onCancel={onCancel} />);
    fireEvent.keyDown(screen.getByLabelText("Notes"), { key: "Escape" });
    expect(onCancel).toHaveBeenCalled();
  });
});
