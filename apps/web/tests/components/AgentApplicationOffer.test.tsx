import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentApplicationDetail from "@/components/AgentApplicationDetail";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const LETTER = { id: "d1", name: "offer.pdf", verification_status: "pending", created_at: "2026-09-20T10:00:00Z" };
const OFFER = { type: "conditional", date: "2026-09-20", deadline: "2026-10-20", conditions: "IELTS 6.5\nFinal transcript", document: { id: "d1", name: "offer.pdf", verification_status: "verified" } };
const detail = (over: Record<string, unknown> = {}) => ({
  id: "a1", agent_student_id: "r1", student: "Asha Rao", has_login: false, university: "Uni One", university_id: "u1", university_slug: "u1",
  course: null, course_id: null, intake: "Fall 2027", status: "university_selection", application_reference: null, submitted_on: null,
  application_deadline: null, offer_deadline: null, nearest_deadline: null, next_action: null, updated_at: "", created_at: "", read_only_reason: null,
  history: [], offer: null, offer_letters: [LETTER],
  ...over,
});

function serve(first: Record<string, unknown>, onPut?: (body: Record<string, unknown>) => Response) {
  const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
    if (init?.method === "PUT") return Promise.resolve(onPut ? onPut(JSON.parse(String(init.body))) : json({ application: detail({ status: "offer", offer: OFFER }) }));
    return Promise.resolve(json({ application: detail(first) }));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function openForm() {
  render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "Record offer" }));
  return screen.getByRole("form", { name: "Record offer" });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentApplicationOffer (AGN-010)", () => {
  it("shows the empty state and opens the form, hiding the other forms", async () => {
    serve({});
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    expect(await screen.findByText("No offer recorded yet.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Record offer" }));
    expect(screen.getByRole("form", { name: "Record offer" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Update status" })).toBeNull();
  });

  it("asks for conditions only for a conditional offer", async () => {
    serve({});
    const form = await openForm();
    fireEvent.click(within(form).getByLabelText("Unconditional"));
    expect(within(form).queryByLabelText(/Conditions/)).toBeNull();
    fireEvent.click(within(form).getByLabelText("Conditional"));
    expect(within(form).getByLabelText(/Conditions/)).toBeRequired();
  });

  it("refuses a deadline before the offer date without calling the server", async () => {
    const fetchMock = serve({});
    const form = await openForm();
    fireEvent.click(within(form).getByLabelText("Unconditional"));
    fireEvent.change(within(form).getByLabelText("Offer date"), { target: { value: "2026-09-20" } });
    const deadline = within(form).getByLabelText("Offer deadline (optional)");
    fireEvent.change(deadline, { target: { value: "2026-09-19" } });
    expect(deadline).toHaveAttribute("min", "2026-09-20"); // the browser's own check blocks the click; the code checks again on submit
    fireEvent.submit(form);
    expect(await screen.findByRole("alert")).toHaveTextContent("Offer deadline cannot be before the offer date");
    expect(fetchMock.mock.calls.some(([, i]) => i?.method === "PUT")).toBe(false);
  });

  it("sends the whole offer with expected_status and shows the saved offer", async () => {
    const fetchMock = serve({});
    const form = await openForm();
    fireEvent.click(within(form).getByLabelText("Conditional"));
    fireEvent.change(within(form).getByLabelText("Offer date"), { target: { value: "2026-09-20" } });
    fireEvent.change(within(form).getByLabelText(/Conditions/), { target: { value: "  IELTS 6.5  " } });
    fireEvent.change(within(form).getByLabelText("Offer letter (optional)"), { target: { value: "d1" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save offer" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Offer saved.");
    const put = fetchMock.mock.calls.find(([, i]) => i?.method === "PUT")!;
    expect(put[0]).toBe("/api/v1/workflows/overseas/agent/crm/applications/a1/offer");
    expect(JSON.parse(String(put[1]!.body))).toEqual({
      offer_type: "conditional", offer_date: "2026-09-20", offer_deadline: null, conditions: "IELTS 6.5", offer_document_id: "d1", expected_status: "university_selection",
    });
    const offer = screen.getByRole("region", { name: "Offer" });
    expect(within(offer).getByText("Conditional")).toBeInTheDocument();
    expect(within(offer).getByRole("button", { name: "Download offer.pdf" })).toBeInTheDocument();
    await waitFor(() => expect(within(offer).getByRole("heading", { name: "Offer" })).toHaveFocus());
  });

  it("keeps the input and focuses the server's words on a 422", async () => {
    serve({}, () => json({ detail: [{ msg: "Value error, Offer date cannot be in the future" }] }, 422));
    const form = await openForm();
    fireEvent.click(within(form).getByLabelText("Unconditional"));
    fireEvent.change(within(form).getByLabelText("Offer date"), { target: { value: "2026-09-20" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save offer" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Offer date cannot be in the future");
    await waitFor(() => expect(alert).toHaveFocus());
    expect(within(screen.getByRole("form", { name: "Record offer" })).getByLabelText("Offer date")).toHaveValue("2026-09-20");
  });

  it("explains how to add an offer letter when none is uploaded", async () => {
    serve({ offer_letters: [] });
    const form = await openForm();
    expect(within(form).queryByLabelText("Offer letter (optional)")).toBeNull();
    expect(within(form).getByRole("link", { name: "Documents" })).toHaveAttribute("href", "/overseas/agent/documents");
  });

  it("shows a recorded offer read-only, with conditions line by line and no buttons", async () => {
    serve({ status: "withdrawn", read_only_reason: "withdrawn", offer: OFFER });
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    const offer = await screen.findByRole("region", { name: "Offer" });
    expect(within(offer).getByText(/IELTS 6.5/)).toHaveClass("offer-conditions");
    expect(within(offer).getByText("2026-10-20")).toBeInTheDocument();
    expect(within(offer).queryByRole("button", { name: /offer$/ })).toBeNull();
  });

  it("prefills Edit offer and Cancel returns focus to it", async () => {
    serve({ status: "offer", offer: OFFER });
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit offer" }));
    const form = screen.getByRole("form", { name: "Edit offer" });
    expect(within(form).getByLabelText("Conditional")).toBeChecked();
    expect(within(form).getByLabelText(/Conditions/)).toHaveValue("IELTS 6.5\nFinal transcript");
    fireEvent.click(within(form).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit offer" })).toHaveFocus());
  });
});
