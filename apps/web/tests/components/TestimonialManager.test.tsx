import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import RatingBadgeForm from "@/components/RatingBadgeForm";
import TestimonialManager from "@/components/TestimonialManager";
import { CONSENT_TEXT, type ManagedTestimonial } from "@/lib/testimonials";

const row: ManagedTestimonial = {
  id: "t1", division: "it", person_name: "Asha Rao", headline: "Placed", quote: "Great mentors.", rating: 5, context: null, photo_url: null,
  published: false, featured: false, display_order: 0, consent_confirmed: false, consent_at: null, has_photo: false, updated_at: null,
};

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function openRow() {
  fetchMock.mockResolvedValueOnce(json(200, [row]));
  render(<TestimonialManager divisions={["it"]} />);
  fireEvent.click(await screen.findByRole("button", { name: /Edit Asha Rao/ }));
}

describe("TestimonialManager (PUB-022)", () => {
  it("lists only the admin's division", async () => {
    fetchMock.mockResolvedValueOnce(json(200, [row]));
    render(<TestimonialManager divisions={["it"]} />);
    expect(await screen.findByRole("cell", { name: "Asha Rao" })).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/cms/manage/testimonials?division=it");
  });

  it("keeps Published disabled until consent is ticked, and unticking consent clears it", async () => {
    await openRow();
    const consent = screen.getByRole("checkbox", { name: CONSENT_TEXT });
    const publish = screen.getByRole("checkbox", { name: "Published" }) as HTMLInputElement;
    expect(publish.disabled).toBe(true);
    fireEvent.click(consent);
    expect(publish.disabled).toBe(false);
    fireEvent.click(publish);
    expect(publish.checked).toBe(true);
    fireEvent.click(consent);
    expect(publish.checked).toBe(false);
    expect(publish.disabled).toBe(true);
  });

  it("asks before deleting and only then calls DELETE", async () => {
    await openRow();
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    fireEvent.click(screen.getByRole("button", { name: "Delete permanently" }));
    expect(confirm).toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    confirm.mockReturnValueOnce(true);
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 })).mockResolvedValueOnce(json(200, []));
    fireEvent.click(screen.getByRole("button", { name: "Delete permanently" }));
    await screen.findByText("Testimonial deleted.");
    expect(fetchMock.mock.calls[1]).toEqual(["/api/v1/cms/testimonials/t1", { method: "DELETE" }]);
  });

  it("shows the server's 422 detail on save", async () => {
    await openRow();
    fetchMock.mockResolvedValueOnce(json(422, { detail: "Record consent before publishing" }));
    fireEvent.click(screen.getByRole("button", { name: "Save testimonial" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Record consent before publishing");
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe("/api/v1/cms/testimonials/t1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).not.toHaveProperty("division");
  });

  it("creates with the chosen division for a Super Admin", async () => {
    fetchMock.mockResolvedValueOnce(json(200, []));
    render(<TestimonialManager divisions={["it", "overseas"]} />);
    await screen.findByText("No testimonials yet.");
    fireEvent.click(screen.getAllByRole("button", { name: "Add testimonial" })[0]);
    fireEvent.change(screen.getByLabelText("Division"), { target: { value: "overseas" } });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Sneha P" } });
    fireEvent.change(screen.getByLabelText("Headline"), { target: { value: "Visa granted" } });
    fireEvent.change(screen.getByLabelText("Quote"), { target: { value: "Clear guidance." } });
    fetchMock.mockResolvedValueOnce(json(201, { ...row, id: "t2", division: "overseas", person_name: "Sneha P" })).mockResolvedValueOnce(json(200, []));
    fireEvent.click(screen.getAllByRole("button", { name: "Add testimonial" })[1]);
    await screen.findByText("Testimonial added.");
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe("/api/v1/cms/testimonials");
    expect(JSON.parse(init.body)).toMatchObject({ division: "overseas", person_name: "Sneha P", published: false, consent_confirmed: false, context: null });
  });

  it("requires name, headline and quote before sending", async () => {
    fetchMock.mockResolvedValueOnce(json(200, []));
    render(<TestimonialManager divisions={["it"]} />);
    await screen.findByText("No testimonials yet.");
    fireEvent.click(screen.getByRole("button", { name: "Add testimonial" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Add testimonial" })[1]);
    expect((await screen.findByRole("alert")).textContent).toBe("Enter the name, headline and quote.");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("RatingBadgeForm (PUB-022)", () => {
  it("loads the badge and saves it with numeric values", async () => {
    fetchMock.mockResolvedValueOnce(json(200, { source_name: "Google", rating: 4.8, review_count: 120, review_url: null, as_of: "2026-10-01", published: false }));
    render(<RatingBadgeForm />);
    const rating = (await screen.findByLabelText("Rating (0.0 to 5.0)")) as HTMLInputElement;
    expect(rating.value).toBe("4.8");
    fireEvent.change(rating, { target: { value: "4.9" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Published" }));
    fetchMock.mockResolvedValueOnce(json(200, { source_name: "Google", rating: 4.9, review_count: 120, review_url: null, as_of: "2026-10-01", published: true }));
    fireEvent.click(screen.getByRole("button", { name: "Save rating badge" }));
    await screen.findByText("Rating badge saved.");
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe("/api/v1/cms/rating-badge");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({ source_name: "Google", rating: 4.9, review_count: 120, review_url: null, as_of: "2026-10-01", published: true });
  });

  it("starts empty when there is no badge yet", async () => {
    fetchMock.mockResolvedValueOnce(json(200, null));
    render(<RatingBadgeForm />);
    expect(((await screen.findByLabelText("Review site")) as HTMLInputElement).value).toBe("Google");
    expect((screen.getByLabelText("Rating (0.0 to 5.0)") as HTMLInputElement).value).toBe("");
  });
});
