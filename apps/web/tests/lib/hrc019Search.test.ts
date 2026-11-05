import { describe, expect, it } from "vitest";

import { activeFilters, EMPTY_SEARCH, FILTERS, paramsOf, searchBody, sortOptions, stateOf } from "@/lib/recruiterCandidateSearch";

const params = (q: string) => new URLSearchParams(q);
const CAT = "0f8fad5b-d9cb-469f-a165-70867728950e";

describe("hrc-019 advanced filters <-> URL <-> body", () => {
  it("reads every new filter from the URL and writes it back unchanged", () => {
    const query = [
      "all=Java", "pref=Docker", "pref=Kubernetes", `cat=${CAT}`, "level=intermediate", "skill_yrs=2", "degree=B.Tech", "spec=CSE", "inst=JNTU",
      "year_min=2018", "year_max=2022", "cgpa_min=7.5", "cgpa_max=10", "fresher=1", "rel_min=2", "rel_max=5", "designation=Developer",
      "industry=Banking", "emp_type=full_time", "emp_type=contract", "country=India", "state=Telangana", "city=Hyderabad", "pref_loc=Pune",
      "relocate=1", "work_mode=remote", "pref_role=Backend", "pref_emp=full_time", "owner=me", "reg_from=2024-01-01", "reg_to=2024-12-31",
      "resume=0", "doc=payslip", "app=interview", "interviewed=1", "cur_min=4", "cur_max=9.5", "min_min=5", "min_max=8", "sal_unknown=1",
      "sort=completeness",
    ].join("&");
    const state = stateOf(params(query));
    expect(state.preferred).toEqual(["Docker", "Kubernetes"]);
    expect(state.sort).toBe("completeness");
    expect(state.more).toMatchObject({ degree: ["B.Tech"], emp_type: ["full_time", "contract"], resume: ["0"], cat: [CAT] });
    expect(stateOf(paramsOf(state))).toEqual(state);
    expect(searchBody(state)).toMatchObject({
      all: ["Java"], preferred: ["Docker", "Kubernetes"], category_ids: [CAT], min_level: "intermediate", skill_min_months: 24, degree: "B.Tech",
      specialisation: "CSE", institution: "JNTU", passing_year_min: 2018, passing_year_max: 2022, cgpa_min: 7.5, cgpa_max: 10, fresher: true,
      relevant_min_months: 24, relevant_max_months: 71, designation: "Developer", industry: "Banking", employment_types: ["full_time", "contract"],
      country: "India", state: "Telangana", city: "Hyderabad", preferred_location: "Pune", willing_to_relocate: true, work_modes: ["remote"],
      preferred_role: "Backend", preferred_employment_types: ["full_time"], owner: "me", registered_from: "2024-01-01", registered_to: "2024-12-31",
      has_resume: false, document_types: ["payslip"], application_statuses: ["interview"], interviewed: true, current_min: 400000,
      current_max: 950000, minimum_min: 500000, minimum_max: 800000, package_unknown: true, sort: "completeness",
    });
  });

  it("drops hand-edited values the API would refuse", () => {
    const state = stateOf(params("all=Java&cgpa_min=11&year_min=1800&level=guru&owner=boss&reg_from=31-12-2024&emp_type=moon&cat=x&sort=salary&resume=maybe"));
    expect(state.more).toEqual({});
    expect(state.sort).toBe("relevance");
    expect(searchBody(state)).toEqual({ all: ["Java"] });
  });

  it("the default sort is left out of the URL and the body", () => {
    expect(paramsOf({ ...EMPTY_SEARCH, all: ["Java"] }).has("sort")).toBe(false);
    expect(searchBody({ ...EMPTY_SEARCH, all: ["Java"] })).toEqual({ all: ["Java"] });
  });

  it("nice-to-have skills or a category alone are a search", () => {
    expect(searchBody({ ...EMPTY_SEARCH, preferred: ["Docker"] })).toEqual({ preferred: ["Docker"] });
    expect(searchBody({ ...EMPTY_SEARCH, more: { cat: [CAT] } })).toEqual({ category_ids: [CAT] });
    expect(searchBody({ ...EMPTY_SEARCH, more: { degree: ["B.Tech"] } })).toBeNull();
  });

  it("lists one removable chip per active filter, and removing one keeps the rest (AC2)", () => {
    const state = stateOf(params("all=Java&degree=B.Tech&emp_type=full_time&emp_type=contract&location=Pune&verified=1&avail=d15&sal_unknown=1&sort=experience"));
    const chips = activeFilters(state, { categories: {} });
    expect(chips.map((c) => c.label)).toEqual([
      "Verified skills only", "Location: Pune", "Availability: 15 days", "Degree: B.Tech", "Employment type: Full time",
      "Employment type: Contract", "Include unknown salary",
    ]);
    const next = chips.find((c) => c.label === "Employment type: Full time")!.clear(state);
    expect(next.more.emp_type).toEqual(["contract"]);
    expect(next.more.degree).toEqual(["B.Tech"]);
    expect(next.location).toBe("Pune");
    expect(next.offset).toBe(0);
    const noDegree = chips.find((c) => c.label === "Degree: B.Tech")!.clear(state);
    expect(noDegree.more.degree).toBeUndefined();
  });

  it("names a category chip from the loaded categories", () => {
    const chips = activeFilters(stateOf(params(`all=Java&cat=${CAT}`)), { categories: { [CAT]: "Pharmacy" } });
    expect(chips.map((c) => c.label)).toEqual(["Skill category: Pharmacy"]);
  });

  it("package filters and the package sort are offered only with the grant", () => {
    expect(FILTERS.filter((f) => f.package).map((f) => f.param)).toEqual(["cur_min", "cur_max", "min_min", "min_max", "sal_unknown"]);
    expect(sortOptions(false).map((o) => o.key)).not.toContain("package");
    expect(sortOptions(true).map((o) => o.key)).toContain("package");
  });
});
