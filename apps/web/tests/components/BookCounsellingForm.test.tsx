import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BookCounsellingForm from "@/components/BookCounsellingForm";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const options = {
  types: [{ key: "career_counselling", label: "Career counselling" }, { key: "it_course_counselling", label: "IT course counselling" }],
  counselors: [{ id: "c1", full_name: "Kavya" }], modes: ["Online", "Phone", "In person"], duration_minutes: 60,
};

function route(post: Response) {
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>((url) =>
    Promise.resolve(String(url).endsWith("/appointment-options") ? res(options) : post));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function fill() {
  fireEvent.change(await screen.findByLabelText("Appointment type"), { target: { value: "it_course_counselling" } });
  fireEvent.change(screen.getByLabelText("Counselor"), { target: { value: "c1" } });
  fireEvent.change(screen.getByLabelText("Date and time (IST)"), { target: { value: "2030-01-02T11:00" } });
}

describe("BookCounsellingForm (tel-016)", () => {
  it("refuses missing fields in place and clears a field's error once it is changed (QA-01)", async () => {
    const fetch = route(res({}));
    render(<BookCounsellingForm leadId="l1" onBooked={() => {}} onCancel={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "Book appointment" }));
    expect(screen.getByText("Choose the appointment type.")).toBeTruthy();
    expect(screen.getByText("Choose a counselor.")).toBeTruthy();
    expect(fetch).toHaveBeenCalledTimes(1); // the options read only: nothing was sent
    fireEvent.change(screen.getByLabelText("Appointment type"), { target: { value: "career_counselling" } });
    expect(screen.queryByText("Choose the appointment type.")).toBeNull();
    expect(screen.getByLabelText("Appointment type").getAttribute("aria-invalid")).toBeNull();
    expect(screen.getByText("Choose a counselor.")).toBeTruthy(); // other fields keep theirs
  });

  it("sends the IST time and hands the booking back", async () => {
    const booked = { id: "a1", code: "CAP-000001" };
    const fetch = route(res(booked, 201));
    const onBooked = vi.fn();
    render(<BookCounsellingForm leadId="l1" onBooked={onBooked} onCancel={() => {}} />);
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
    await waitFor(() => expect(onBooked).toHaveBeenCalledWith(booked));
    const [url, init] = fetch.mock.calls[1];
    expect(url).toBe("/api/v1/telecaller/leads/l1/appointments");
    expect(JSON.parse(String(init?.body))).toEqual({ appointment_type: "it_course_counselling", counselor_id: "c1", scheduled_at: "2030-01-02T11:00:00+05:30", mode: "Online" });
  });

  it("names the counselor's busy time on a clash (AP1)", async () => {
    route(res({ detail: { message: "The counselor already has an appointment at this time", code: "counselor_busy", matches: [{ scheduled_at: "2030-01-02T05:30:00+00:00", duration_minutes: 60 }] } }, 409));
    render(<BookCounsellingForm leadId="l1" onBooked={() => {}} onCancel={() => {}} />);
    await fill();
    fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Busy: 02 Jan 2030, 11:00 IST");
    expect(screen.getByText("The counselor is busy at this time.")).toBeTruthy();
  });

  it("says so when the options cannot load, with a retry", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({}, 500))));
    render(<BookCounsellingForm leadId="l1" onBooked={() => {}} onCancel={() => {}} />);
    expect((await screen.findByRole("alert")).textContent).toContain("Unable to load the booking form.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });
});
