import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PortfolioEntryForm from "@/components/PortfolioEntryForm";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PortfolioEntryForm", () => {
  it("requires a title before submitting", async () => {
    render(<PortfolioEntryForm studentId="s1" section="project" onDone={() => {}} onCancel={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText(/enter a title/i)).toBeInTheDocument();
  });

  it("shows a server error on failure", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: "date_to must not be before date_from" }) }) as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="project" onDone={() => {}} onCancel={() => {}} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "A project" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("date_to must not be before date_from");
  });

  it("calls onDone after a successful save", async () => {
    const onDone = vi.fn();
    global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: "e1", section: "project", title: "A project" }) }) as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="project" onDone={onDone} onCancel={() => {}} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "A project" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("PATCHes to the entry URL and omits section when editing an existing entry", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: "e1", section: "project", title: "Updated" }) });
    global.fetch = fetchMock as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="project" entryId="e1" initial={{ title: "Old", description: null, organization: null, date_from: null, date_to: null }} onDone={() => {}} onCancel={() => {}} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "Updated" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/v1/school/students/s1/portfolio/entries/e1", expect.objectContaining({ method: "PATCH" }));
      const [, init] = fetchMock.mock.calls[0];
      const body = JSON.parse(init.body as string);
      expect(body).not.toHaveProperty("section");
      expect(body.title).toBe("Updated");
    });
  });
});

// ENH-024 -- docs/superpowers/specs/2026-09-28-enh-024-skill-india-certification-design.md §6.
describe("PortfolioEntryForm — Skill India", () => {
  const ok = () => vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: "e1" }) });
  const bodyOf = (m: ReturnType<typeof vi.fn>) => JSON.parse(m.mock.calls[0][1].body as string);

  it("offers the Skill India checkbox only when adding a certification", () => {
    const { unmount } = render(<PortfolioEntryForm studentId="s1" section="award" onDone={() => {}} onCancel={() => {}} />);
    expect(screen.queryByLabelText(/skill india certification/i)).not.toBeInTheDocument();
    unmount();
    render(<PortfolioEntryForm studentId="s1" section="certification" onDone={() => {}} onCancel={() => {}} />);
    expect(screen.getByRole("checkbox", { name: /skill india certification/i })).not.toBeChecked();
    expect(screen.queryByRole("group", { name: /skill india details/i })).not.toBeInTheDocument();
  });

  it("reveals the details fieldset and relabels Organization as Issuing body", () => {
    render(<PortfolioEntryForm studentId="s1" section="certification" onDone={() => {}} onCancel={() => {}} />);
    fireEvent.click(screen.getByRole("checkbox", { name: /skill india certification/i }));
    const group = screen.getByRole("group", { name: /skill india details/i });
    expect(within(group).getByLabelText(/status/i)).toHaveValue("");
    expect(within(group).getByLabelText(/certificate number/i)).toHaveAccessibleDescription(/required once certified/i);
    expect(within(group).getByLabelText(/issue date/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/issuing body/i)).toBeInTheDocument();
  });

  it("requires a status, and a number and issue date once certified, focusing the first problem", async () => {
    const fetchMock = ok();
    global.fetch = fetchMock as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="certification" onDone={() => {}} onCancel={() => {}} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "Retail Sales Associate" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /skill india certification/i }));
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText("Choose a status.")).toBeInTheDocument();
    expect(screen.getByLabelText(/status/i)).toHaveAttribute("aria-invalid", "true");
    await waitFor(() => expect(screen.getByLabelText(/status/i)).toHaveFocus());
    fireEvent.change(screen.getByLabelText(/status/i), { target: { value: "certified" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText("Enter the certificate number.")).toBeInTheDocument();
    expect(screen.getByText("Enter the issue date.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText(/certificate number/i)).toHaveFocus());
    expect(fetchMock).not.toHaveBeenCalled();
  });

  // QA24-06: a Skill India field's error goes away as soon as that field is edited, not only on the next Save.
  it("clears each Skill India error when its own field is edited", async () => {
    global.fetch = ok() as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="certification" onDone={() => {}} onCancel={() => {}} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "Retail" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /skill india certification/i }));
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText("Choose a status.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/status/i), { target: { value: "certified" } });
    expect(screen.queryByText("Choose a status.")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/status/i)).not.toHaveAttribute("aria-invalid");
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText("Enter the certificate number.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/certificate number/i), { target: { value: "SI-1" } });
    expect(screen.queryByText("Enter the certificate number.")).not.toBeInTheDocument();
    expect(screen.getByText("Enter the issue date.")).toBeInTheDocument(); // an untouched field keeps its error
    fireEvent.change(screen.getByLabelText(/issue date/i), { target: { value: "2026-05-01" } });
    expect(screen.queryByText("Enter the issue date.")).not.toBeInTheDocument();
  });

  it("POSTs the tag and details when ticked", async () => {
    const fetchMock = ok();
    global.fetch = fetchMock as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="certification" onDone={() => {}} onCancel={() => {}} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "Retail Sales Associate" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /skill india certification/i }));
    fireEvent.change(screen.getByLabelText(/status/i), { target: { value: "certified" } });
    fireEvent.change(screen.getByLabelText(/certificate number/i), { target: { value: " SI-9 " } });
    fireEvent.change(screen.getByLabelText(/issue date/i), { target: { value: "2026-05-01" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(bodyOf(fetchMock)).toMatchObject({ section: "certification", certification_type: "skill_india", certification_status: "certified", certificate_number: "SI-9", issued_on: "2026-05-01" });
  });

  it("sends no Skill India fields when unticked again", async () => {
    const fetchMock = ok();
    global.fetch = fetchMock as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="certification" onDone={() => {}} onCancel={() => {}} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "First aid" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /skill india certification/i }));
    fireEvent.change(screen.getByLabelText(/status/i), { target: { value: "enrolled" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /skill india certification/i }));
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = bodyOf(fetchMock);
    for (const key of ["certification_type", "certification_status", "certificate_number", "issued_on"]) expect(body).not.toHaveProperty(key);
  });

  it("edits a tagged entry without a checkbox and never PATCHes the tag", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: "e1" }) });
    global.fetch = fetchMock as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="certification" entryId="e1" initial={{ title: "Retail", description: null, organization: null, date_from: null, date_to: null, certification_type: "skill_india", certification_status: "enrolled", certificate_number: null, issued_on: null }} onDone={() => {}} onCancel={() => {}} />);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText("Skill India certification")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/status/i), { target: { value: "in_progress" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = bodyOf(fetchMock);
    expect(body).not.toHaveProperty("certification_type");
    expect(body.certification_status).toBe("in_progress");
  });

  it("sends no Skill India fields when editing a plain entry", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: "e1" }) });
    global.fetch = fetchMock as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="certification" entryId="e1" initial={{ title: "First aid", description: null, organization: null, date_from: null, date_to: null }} onDone={() => {}} onCancel={() => {}} />);
    expect(screen.queryByText("Skill India certification")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = bodyOf(fetchMock);
    for (const key of ["certification_type", "certification_status", "certificate_number", "issued_on"]) expect(body).not.toHaveProperty(key);
  });

  it("disables the Skill India fields while saving", async () => {
    global.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;
    render(<PortfolioEntryForm studentId="s1" section="certification" onDone={() => {}} onCancel={() => {}} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: "Retail" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /skill india certification/i }));
    fireEvent.change(screen.getByLabelText(/status/i), { target: { value: "enrolled" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByRole("button", { name: /saving/i })).toBeDisabled();
    expect(screen.getByLabelText(/status/i)).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: /skill india certification/i })).toBeDisabled();
  });
});
