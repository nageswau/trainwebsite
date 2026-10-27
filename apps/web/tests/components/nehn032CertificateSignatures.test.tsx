import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminCertificateSignaturesPanel from "@/components/AdminCertificateSignaturesPanel";

// nehn-032 (DEC-SCOPE-300): one card per signature slot -- the current image, name and designation; saving with a PNG uploads a new
// version, saving without one edits the details of the current version.
const URL = "/api/v1/admin/certificate-signatories";
const founder = { id: "f1", role: "founder", display_name: "Asha Founder", designation: "Founder & Director", active: true, active_from: "2026-10-27T00:00:00Z", active_to: null };
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));

type Routes = Record<string, (init?: RequestInit) => Promise<Response>>;
function stubFetch(routes: Routes) {
  const mock = vi.fn((url: string, init?: RequestInit) => (routes[`${init?.method ?? "GET"} ${url}`] ?? (() => json({}, 404)))(init));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("certificate signatures card", () => {
  it("shows a loading state, then the current signature and an empty slot", async () => {
    stubFetch({ [`GET ${URL}`]: () => json({ items: [founder, { ...founder, id: "f0", active: false, display_name: "Old Founder" }] }) });
    render(<AdminCertificateSignaturesPanel />);
    expect(screen.getByText(/Loading the certificate signatures/)).toBeInTheDocument();
    const image = await screen.findByRole("img", { name: "Asha Founder signature" });
    expect(image).toHaveAttribute("src", `${URL}/f1/image`);
    expect(screen.queryByText("Old Founder")).toBeNull();
    const coordinator = screen.getByRole("group", { name: "Coordinator signature" });
    expect(within(coordinator).getByText(/No signature uploaded/)).toBeInTheDocument();
    // QA32-01: no preview link while a slot is empty (the preview would only answer 409)
    expect(screen.queryByRole("link", { name: /Preview certificate/ })).toBeNull();
    expect(screen.getByText("Upload both signatures to preview the certificate.")).toBeInTheDocument();
  });

  it("uploads a new version with the chosen PNG", async () => {
    const mock = stubFetch({
      [`GET ${URL}`]: () => json({ items: [founder] }),
      [`POST ${URL}`]: () => json({ ...founder, id: "c1", role: "coordinator", display_name: "Nisha R", designation: "IT Coordinator" }, 201),
    });
    render(<AdminCertificateSignaturesPanel />);
    const slot = await screen.findByRole("group", { name: "Coordinator signature" });
    fireEvent.change(within(slot).getByLabelText("Name"), { target: { value: "Nisha R" } });
    fireEvent.change(within(slot).getByLabelText("Designation"), { target: { value: "IT Coordinator" } });
    const file = new File([new Uint8Array([137, 80, 78, 71])], "sig.png", { type: "image/png" });
    fireEvent.change(within(slot).getByLabelText(/Signature image/), { target: { files: [file] } });
    // jsdom keeps a required file input invalid even with `files` set, so submit the form itself (a browser submits on the click)
    fireEvent.submit(within(slot).getByRole("button", { name: "Save coordinator signature" }).closest("form")!);
    expect(await within(slot).findByRole("status")).toHaveTextContent("Coordinator signature saved");
    const body = mock.mock.calls.find(([u, init]) => u === URL && init?.method === "POST")?.[1]?.body as FormData;
    expect(body.get("role")).toBe("coordinator");
    expect(body.get("display_name")).toBe("Nisha R");
    expect((body.get("file") as File).name).toBe("sig.png");
    expect(await within(slot).findByRole("img", { name: "Nisha R signature" })).toBeInTheDocument();
    // both slots filled now: the preview opens in a new tab
    expect(screen.getByRole("link", { name: /Preview certificate/ })).toHaveAttribute("href", "/api/v1/admin/certificates/preview");
  });

  it("an empty slot needs an image", async () => {
    const mock = stubFetch({ [`GET ${URL}`]: () => json({ items: [] }) });
    render(<AdminCertificateSignaturesPanel />);
    const slot = await screen.findByRole("group", { name: "Founder signature" });
    expect(within(slot).getByLabelText(/Signature image/)).toBeRequired();
    expect(mock).toHaveBeenCalledTimes(1);
  });

  it("edits the details without an image and shows a refusal as an alert", async () => {
    const mock = stubFetch({
      [`GET ${URL}`]: () => json({ items: [founder] }),
      [`PATCH ${URL}/f1`]: () => json({ detail: "This signature version is no longer active" }, 409),
    });
    render(<AdminCertificateSignaturesPanel />);
    const slot = await screen.findByRole("group", { name: "Founder signature" });
    expect(within(slot).getByLabelText(/Signature image/)).not.toBeRequired();
    fireEvent.change(within(slot).getByLabelText("Designation"), { target: { value: "Chairperson" } });
    fireEvent.click(within(slot).getByRole("button", { name: "Save founder signature" }));
    expect(await within(slot).findByRole("alert")).toHaveTextContent("This signature version is no longer active");
    const call = mock.mock.calls.find(([u, init]) => u === `${URL}/f1` && init?.method === "PATCH");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ display_name: "Asha Founder", designation: "Chairperson" });
  });

  it("shows a load failure", async () => {
    stubFetch({ [`GET ${URL}`]: () => json({ detail: "You do not have permission to manage certificate signatures" }, 403) });
    render(<AdminCertificateSignaturesPanel />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("You do not have permission to manage certificate signatures"));
  });
});
