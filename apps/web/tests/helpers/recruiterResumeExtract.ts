import type { Extraction } from "@/lib/recruiterResumeExtract";

// rec-012: one extraction as the API returns it (the source sentence's five skills, Java already on the profile).
export const extraction = (over: Partial<Extraction> = {}): Extraction => ({
  version: 2, no_text: false, truncated: false, text_chars: 480, extracted_at: "2026-10-09T05:00:00Z",
  skills: [
    { skill: { id: "K-java", name: "Java", active: true }, category: { id: "G1", name: "Programming" }, matched: "Java", on_profile: true },
    { skill: { id: "K-boot", name: "Spring Boot", active: true }, category: { id: "G2", name: "Java Technologies" }, matched: "Spring Boot", on_profile: false },
    { skill: { id: "K-rest", name: "REST API", active: true }, category: { id: "G2", name: "Java Technologies" }, matched: "REST APIs", on_profile: false },
  ],
  qualification: "B.Tech", experience_months: 36, location: "Pune",
  job_titles: ["Senior Java Developer"], certifications: ["AWS Certified Developer"], industries: ["Banking & Finance"],
  ...over,
});
