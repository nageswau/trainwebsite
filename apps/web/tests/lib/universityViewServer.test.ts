import { afterEach, describe, expect, it, vi } from "vitest";

const serverApi = vi.fn();
vi.mock("@/lib/api", async (original) => ({ ...(await original<typeof import("@/lib/api")>()), serverApi: (...args: unknown[]) => serverApi(...args) }));

import { ApiError } from "@/lib/api";
import { loadUniversityView } from "@/lib/universityViewServer";

afterEach(() => {
  serverApi.mockReset();
});

describe("loadUniversityView (upc-030 QA-01)", () => {
  it("reads a well-formed id's view from the API", async () => {
    serverApi.mockResolvedValue({ slice: "bdm" });
    const id = "3f2b6a8e-1c4d-4e5f-8a9b-0c1d2e3f4a5b";
    expect(await loadUniversityView(id)).toEqual({ slice: "bdm" });
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/universities/${id}/view`);
  });

  it("answers a malformed id as not found, without calling the API (it would answer 422)", async () => {
    await expect(loadUniversityView("not-a-uuid")).rejects.toEqual(new ApiError("University not found", 404));
    expect(serverApi).not.toHaveBeenCalled();
  });
});
