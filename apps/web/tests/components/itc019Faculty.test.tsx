import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminFacultyProfiles from "@/components/AdminFacultyProfiles";
import MyFaculty from "@/components/MyFaculty";
import TrainerProfileForm from "@/components/TrainerProfileForm";
import { type OwnProfile, OWN_PROFILE_API, studentPreview } from "@/lib/faculty";

// itc-019 (DEC-SCOPE-346): the trainer's own profile editor, the IT Admin's picker, and the student's My faculty card.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const own = (over: Partial<OwnProfile> = {}): OwnProfile => ({
  trainer_id: "t1", name: "Asha Rao", designation: "Senior Trainer", expertise: ["Python", "Django"], bio: "Ten years.", office_hours: "Mon–Fri 6–7 pm",
  contact_route: "in_app", show_email: false, show_phone: false, show_photo: true, show_bio: true, show_office_hours: true,
  account_email: "asha@example.com", account_phone: "+919800000019", photo_url: null, ...over,
});

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn(() => Promise.resolve(res(own())));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("studentPreview", () => {
  it("leaves hidden fields out, like the API (AC1)", () => {
    const view = studentPreview(own({ show_bio: false }));
    expect(view).not.toHaveProperty("phone");
    expect(view).not.toHaveProperty("email");
    expect(view).not.toHaveProperty("bio");
    expect(view.office_hours).toBe("Mon–Fri 6–7 pm");
  });
  it("shows a visible phone and falls back to in-app when the channel is gone", () => {
    expect(studentPreview(own({ show_phone: true, contact_route: "phone" }))).toMatchObject({ phone: "+919800000019", contact_route: "phone" });
    expect(studentPreview(own({ show_phone: true, contact_route: "phone", account_phone: null }))).toMatchObject({ contact_route: "in_app" });
  });
});

describe("TrainerProfileForm", () => {
  it("loads the profile and saves office hours with PUT", async () => {
    render(<TrainerProfileForm />);
    const hours = await screen.findByLabelText("Office hours");
    expect(fetchMock).toHaveBeenCalledWith(OWN_PROFILE_API, expect.objectContaining({ method: "GET" }));
    fireEvent.change(hours, { target: { value: "Sat 10–11 am" } });
    fetchMock.mockImplementationOnce(() => Promise.resolve(res(own({ office_hours: "Sat 10–11 am" }))));
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));
    await screen.findByText("Profile saved.");
    const [url, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(url).toBe(OWN_PROFILE_API);
    expect(init.method).toBe("PUT");
    expect(JSON.parse(String(init.body))).toMatchObject({ office_hours: "Sat 10–11 am", expertise: ["Python", "Django"], show_phone: false });
    expect(JSON.parse(String(init.body))).not.toHaveProperty("account_phone");
  });

  it("shows the server's refusal", async () => {
    render(<TrainerProfileForm />);
    await screen.findByLabelText("Office hours");
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({ detail: "To be contacted by phone, show your phone" }, 422)));
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByText("To be contacted by phone, show your phone")).toBeTruthy();
  });

  it("previews only what students will see", async () => {
    render(<TrainerProfileForm />);
    const preview = await screen.findByRole("region", { name: "What students see" });
    expect(within(preview).queryByText("+919800000019")).toBeNull();
    fireEvent.click(screen.getByLabelText("Show my phone to students"));
    expect(within(preview).getByText("+919800000019")).toBeTruthy();
  });

  it("uploads a photo as multipart to the photo route", async () => {
    render(<TrainerProfileForm />);
    const input = await screen.findByLabelText(/PNG, JPEG or WebP/);
    fireEvent.change(input, { target: { files: [new File(["x"], "me.png", { type: "image/png" })] } });
    fetchMock.mockImplementationOnce(() => Promise.resolve(res(own({ photo_url: "/api/v1/files/signed/tok" }))));
    fireEvent.click(screen.getByRole("button", { name: "Upload photo" }));
    await screen.findByText("Photo saved.");
    const [url, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
    expect(url).toBe(`${OWN_PROFILE_API}/photo`);
    expect(init.method).toBe("PUT");
    expect(init.body).toBeInstanceOf(FormData);
  });

  it("shows an error with a retry when loading fails", async () => {
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({ detail: "boom" }, 500)));
    render(<TrainerProfileForm />);
    expect(await screen.findByText("Unable to load the profile.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByLabelText("Office hours")).toBeTruthy();
  });
});

describe("AdminFacultyProfiles", () => {
  it("lists IT trainers and opens the chosen trainer's profile", async () => {
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(url.startsWith("/api/v1/admin/users") ? res([{ id: "t1", name: "Asha Rao" }]) : res(own())),
    );
    render(<AdminFacultyProfiles />);
    const picker = await screen.findByLabelText("Trainer");
    await screen.findByRole("option", { name: "Asha Rao" });
    fireEvent.change(picker, { target: { value: "t1" } });
    expect(await screen.findByLabelText("Office hours")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/it/trainers/t1/profile", expect.objectContaining({ method: "GET" }));
  });
});

describe("MyFaculty", () => {
  it("shows each batch's trainer and no hidden details", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(res({ items: [
      { batch_id: "b1", batch: "PY-DEC", program: "Python", faculty: { trainer_id: "t1", name: "Asha Rao", designation: "Senior Trainer", expertise: ["Python"], contact_route: "in_app", office_hours: "Mon–Fri 6–7 pm" } },
      { batch_id: "b2", batch: "JS-JAN", program: "JavaScript", faculty: null },
    ] })));  // prettier-ignore
    render(<MyFaculty />);
    expect(await screen.findByRole("heading", { name: "Asha Rao" })).toBeTruthy();
    expect(screen.getByText("Mon–Fri 6–7 pm")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Questions page" }).getAttribute("href")).toBe("/it/student/questions");
    expect(screen.getByText("Trainer not assigned yet.")).toBeTruthy();
  });

  it("explains an empty list and a failed load", async () => {
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({ items: [] })));
    render(<MyFaculty />);
    expect(await screen.findByText(/Your trainers appear here once you are enrolled/)).toBeTruthy();
    cleanup();
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({}, 500)));
    render(<MyFaculty />);
    expect(await screen.findByText("Unable to load your faculty.")).toBeTruthy();
  });
});

describe("photo states", () => {
  it("renders a photo with alt text when shown", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(res({ items: [{ batch_id: "b1", batch: "PY", program: "Python", faculty: { trainer_id: "t1", name: "Asha Rao", designation: null, expertise: [], contact_route: "phone", phone: "+91 98", photo_url: "/p.png" } }] })));
    render(<MyFaculty />);
    expect(await screen.findByRole("img", { name: "Photo of Asha Rao" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "+91 98" }).getAttribute("href")).toBe("tel:+9198");
  });
});

it("waits for the network before showing anything", async () => {
  fetchMock.mockImplementation(() => new Promise(() => undefined));
  render(<MyFaculty />);
  await waitFor(() => expect(screen.getByText("Loading your faculty…")).toBeTruthy());
});
