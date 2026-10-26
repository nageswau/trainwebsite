// nehn-036 (DEC-SCOPE-285 I4-I5): the curated course icons (= models.COURSE_ICONS, the API's order) and the automatic icon. A course
// with no chosen icon (null) shows the first rule its category matches -- case-insensitive, whole words, in RULES order so "Data
// Science" is data and "Tourism Management" hospitality -- or the general icon. A chosen icon always wins.
export const COURSE_ICONS = ["ai", "security", "data", "computing", "engineering", "business", "health", "hospitality", "law", "education", "arts", "science", "general"] as const;
export type CourseIconKey = (typeof COURSE_ICONS)[number];

export const ICON_LABELS: Record<CourseIconKey, string> = {
  ai: "Artificial intelligence", security: "Cyber security", data: "Data & analytics", computing: "Computing", engineering: "Engineering",
  business: "Business & management", health: "Health & medicine", hospitality: "Hospitality & tourism", law: "Law", education: "Education",
  arts: "Arts & design", science: "Science", general: "General",
};

const RULES: [CourseIconKey, RegExp][] = [
  ["ai", /\b(ai|artificial intelligence|machine learning|robotics)\b/i],
  ["security", /\b(cyber|cybersecurity|security)\b/i],
  ["data", /\b(data|analytics|statistics)\b/i],
  ["computing", /\b(computer|computing|software|informatics|it|information technology|programming)\b/i],
  ["engineering", /\b(engineering|mechanical|civil|electrical|electronics|aerospace)\b/i],
  ["health", /\b(health|healthcare|medicine|medical|nursing|pharmacy|biomedical|dentistry)\b/i],
  ["hospitality", /\b(hospitality|tourism|hotel|culinary)\b/i],
  ["law", /\b(law|legal|llm)\b/i],
  ["education", /\b(education|teaching)\b/i],
  ["business", /\b(business|mba|management|finance|accounting|marketing|economics|commerce)\b/i],
  ["arts", /\b(arts?|design|media|music|film|fashion|architecture)\b/i],
  ["science", /\b(sciences?|physics|chemistry|biology|mathematics|maths?)\b/i],
];

const isKey = (value: string | null | undefined): value is CourseIconKey => (COURSE_ICONS as readonly string[]).includes(value ?? "");

/** The icon a course shows: its chosen key, else the subject its category names, else "general". */
export function courseIconKey(icon: string | null | undefined, category: string): CourseIconKey {
  if (isKey(icon)) return icon;
  return RULES.find(([, words]) => words.test(category))?.[0] ?? "general";
}
