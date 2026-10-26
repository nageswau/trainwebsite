import { afterEach, describe, expect, it, vi } from "vitest";

import { uploadFile } from "@/lib/uploadFile";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const file = new File(["%PDF-1.4"], "cv.pdf", { type: "application/pdf" });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("uploadFile (nehn-003)", () => {
  it("returns the local-upload url", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json(200, { url: "/local-files/uploads/a-cv.pdf" }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(uploadFile(file)).resolves.toBe("/local-files/uploads/a-cv.pdf");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shows the server's refusal instead of falling back to the presign flow", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json(415, { detail: "The file's contents do not match its type" }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(uploadFile(file)).rejects.toThrow("The file's contents do not match its type");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("uses the presigned upload when the server is in S3 mode", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(400, { detail: "Use presigned S3 upload" }))
      .mockResolvedValueOnce(json(200, { key: "uploads/k-cv.pdf", upload_url: "https://bucket.example/put" }))
      .mockResolvedValueOnce(new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(uploadFile(file)).resolves.toBe("uploads/k-cv.pdf");
    expect(fetchMock.mock.calls[2][0]).toBe("https://bucket.example/put");
  });
});
