import { afterEach, describe, expect, it, vi } from "vitest";

const serverApi = vi.fn();
vi.mock("@/lib/api", async (original) => ({ ...(await original<typeof import("@/lib/api")>()), serverApi: (...args: unknown[]) => serverApi(...args) }));

import { ApiError } from "@/lib/api";
import { loadUniversity } from "@/lib/universitiesServer";

afterEach(() => serverApi.mockReset());

describe("loadUniversity (upc-003 QA-01)", () => {
  it("reads a well-formed id from the API", async () => {
    serverApi.mockResolvedValue({ university: { id: "x" } });
    const id = "3f2b6a8e-1c4d-4e5f-8a9b-0c1d2e3f4a5b";
    expect(await loadUniversity(id)).toEqual({ id: "x" });
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/partnership/universities/${id}`);
  });

  it("answers a malformed id as not found, without calling the API", async () => {
    await expect(loadUniversity("not-a-uuid")).rejects.toEqual(new ApiError("University not found", 404));
    expect(serverApi).not.toHaveBeenCalled();
  });
});
