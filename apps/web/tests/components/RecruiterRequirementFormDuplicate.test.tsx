import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterRequirementForm from "@/components/RecruiterRequirementForm";

// hrc-005 (DEC-SCOPE-381 V5/V8, AC2-AC3): a 409 `possible_duplicate` shows the matches; "Save anyway" needs a reason and re-sends with
// it; "Go back" keeps the entry. The location is not required when a city is given (V3).
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const duplicate = {
  code: "possible_duplicate", message: "This may be a duplicate of a live job requirement", total: 1,
  matches: [{ id: "J1", code: "REQ-000111", title: "Data Engineer", location: "Pune", status_label: "Sourcing", requisition_reference: "RQ-9" }],
};
const saved = { requirement: { id: "J2", code: "REQ-000112" } };

let posts: Record<string, unknown>[];
let replies: Response[];
const onSaved = vi.fn();

beforeEach(() => {
  posts = [];
  onSaved.mockReset();
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posts.push(JSON.parse(String(init.body)));
        return Promise.resolve(replies.shift()!);
      }
      if (url.includes("/statuses")) return Promise.resolve(res({ statuses: [], vocabularies: {}, expiring_days: 7 }));
      return Promise.resolve(res({ items: [], total: 0, limit: 100, offset: 0 }));
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const field = (label: RegExp) => screen.getByLabelText(label) as HTMLInputElement;
const company = { id: "C1", label: "Acme", detail: "CMP-1" };

function fill() {
  render(<RecruiterRequirementForm mode="create" company={company} onSaved={onSaved} onCancel={vi.fn()} />);
  fireEvent.change(field(/^Job title/), { target: { value: "Data Engineer" } });
  fireEvent.change(field(/^City/), { target: { value: "Pune" } });
}

describe("RecruiterRequirementForm — possible duplicate", () => {
  it("lists the matches and saves anyway only with a reason", async () => {
    replies = [res({ detail: duplicate }, 409), res(saved, 201)];
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Save requirement" }));
    const panel = await screen.findByRole("region", { name: "Possible duplicate" });
    expect(panel).toHaveTextContent("REQ-000111");
    expect(panel).toHaveTextContent("Data Engineer");
    expect(screen.getByRole("link", { name: /REQ-000111/ })).toHaveAttribute("href", "/recruiter/requirements/J1");
    expect(posts[0]).not.toHaveProperty("location"); // V3: the city is enough

    fireEvent.click(screen.getByRole("button", { name: "Save anyway" }));
    expect(await screen.findByText("Give a reason to save anyway")).toBeInTheDocument();
    expect(posts).toHaveLength(1);

    fireEvent.change(field(/^Why is this not a duplicate/), { target: { value: "Second batch" } });
    fireEvent.click(screen.getByRole("button", { name: "Save anyway" }));
    await vi.waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(posts[1]).toMatchObject({ title: "Data Engineer", city: "Pune", duplicate_reason: "Second batch" });
  });

  it("Go back closes the panel and keeps what was typed", async () => {
    replies = [res({ detail: duplicate }, 409)];
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Save requirement" }));
    await screen.findByRole("region", { name: "Possible duplicate" });
    fireEvent.click(screen.getByRole("button", { name: "Go back" }));
    expect(screen.queryByRole("region", { name: "Possible duplicate" })).toBeNull();
    expect(field(/^Job title/).value).toBe("Data Engineer");
  });

  it("asks for the location or the city before sending", () => {
    render(<RecruiterRequirementForm mode="create" company={company} onSaved={onSaved} onCancel={vi.fn()} />);
    fireEvent.change(field(/^Job title/), { target: { value: "Data Engineer" } });
    fireEvent.click(screen.getByRole("button", { name: "Save requirement" }));
    expect(screen.getByText("Enter the job location or its city")).toBeInTheDocument();
    expect(posts).toHaveLength(0);
  });
});
