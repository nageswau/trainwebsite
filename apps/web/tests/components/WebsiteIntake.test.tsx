import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CandidateRegisterForm from "@/components/CandidateRegisterForm";
import CareerApply from "@/components/CareerApply";
import { MOVED_LABEL } from "@/lib/recruiterDuplicates";
import { captureUtm, readUtm, utmFrom } from "@/lib/utm";

// hrc-023 (DEC-SCOPE-387): the visit's campaign (W1), the job application with consent and honeypot (W4/W6), the registration's UTM
// (W2) and the merge's "website applications" count (W10).
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
beforeEach(() => window.sessionStorage.clear());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function fill(label: RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

describe("utm", () => {
  it("keeps only the five standard keys, trimmed", () => {
    expect(utmFrom("?utm_source=%20linkedin%20&utm_medium=&gclid=x&utm_campaign=nov")).toEqual({ utm_source: "linkedin", utm_campaign: "nov" });
    expect(utmFrom("?q=java")).toBeNull();
  });

  it("keeps the first touch of the visit", () => {
    captureUtm("?utm_source=google");
    captureUtm("?utm_source=bing");
    expect(readUtm("")).toEqual({ utm_source: "google" });
  });

  it("falls back to the current URL when nothing was captured", () => {
    expect(readUtm("?utm_campaign=direct")).toEqual({ utm_campaign: "direct" });
  });
});

describe("CareerApply", () => {
  function fillApplication() {
    fireEvent.click(screen.getByRole("button", { name: "Apply online" }));
    fill(/Full name/, "Meera W");
    fill(/^Email/, "meera@example.com");
    const file = new File(["%PDF-1.4"], "cv.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText(/Resume/), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("checkbox"));
  }

  it("sends the consent version and the visit's UTM, then offers an account with the same email", async () => {
    captureUtm("?utm_source=linkedin&utm_campaign=java-nov");
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(res({ url: "/local-files/career-resumes/a.pdf" }, 201))
      .mockResolvedValueOnce(res({ id: "1", tracking_code: "EDU-CAREER-ABC", status: "submitted" }, 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<CareerApply jobId="job-1" jobTitle="Java Developer" />);
    fillApplication();
    fireEvent.submit(screen.getByRole("button", { name: "Submit application" }).closest("form")!);
    expect(await screen.findByText(/Save your tracking code/)).toHaveTextContent("EDU-CAREER-ABC");
    const [url, init] = fetchMock.mock.calls[1] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/public/jobs/job-1/apply");
    const body = JSON.parse(String(init.body));
    expect(body).toMatchObject({ full_name: "Meera W", email: "meera@example.com", consent_version: "candidate-v1",
                                 utm: { utm_source: "linkedin", utm_campaign: "java-nov" } });  // prettier-ignore
    expect(body).not.toHaveProperty("website"); // the honeypot is empty for a person
    expect(screen.getByRole("link", { name: "create a candidate account" })).toHaveAttribute("href", "/it/careers/register?email=meera%40example.com");
  });

  it("shows the server's message and keeps the form on a refusal", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(res({ url: "/local-files/career-resumes/a.pdf" }, 201))
      .mockResolvedValueOnce(res({ detail: "Too many applications from this network -- try again later" }, 429));
    vi.stubGlobal("fetch", fetchMock);
    render(<CareerApply jobId="job-1" jobTitle="Java Developer" />);
    fillApplication();
    fireEvent.submit(screen.getByRole("button", { name: "Submit application" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many applications");
    expect(screen.getByRole("button", { name: "Submit application" })).toBeEnabled();
  });

  it("says the upload failed without calling the apply route", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail: "Resume must be PDF, DOC or DOCX" }, 415));
    vi.stubGlobal("fetch", fetchMock);
    render(<CareerApply jobId="job-1" jobTitle="Java Developer" />);
    fillApplication();
    fireEvent.submit(screen.getByRole("button", { name: "Submit application" }).closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Resume upload failed");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("hides the honeypot from assistive technology", () => {
    render(<CareerApply jobId="job-1" jobTitle="Java Developer" />);
    fireEvent.click(screen.getByRole("button", { name: "Apply online" }));
    expect(screen.queryByRole("textbox", { name: "Website" })).toBeNull();
  });
});

describe("CandidateRegisterForm (hrc-023)", () => {
  it("sends the visit's UTM with the registration", async () => {
    captureUtm("?utm_medium=email");
    const fetchMock = vi.fn(() => Promise.resolve(res({ accepted: true }, 202)));
    vi.stubGlobal("fetch", fetchMock);
    render(<CandidateRegisterForm />);
    fill(/Full name/, "Asha K");
    fill(/^Email/, "asha@example.com");
    fill(/^Password/, "Candidate@12345");
    fill(/Confirm password/, "Candidate@12345");
    fireEvent.submit(screen.getByRole("button", { name: "Create candidate account" }).closest("form")!);
    await screen.findByRole("status");
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toMatchObject({ utm: { utm_medium: "email" } });
  });
});

describe("merge preview labels", () => {
  it("counts website applications", () => {
    expect(MOVED_LABEL).toContainEqual(["career_applications", "website applications"]);
  });
});
