// The generated tile a course card shows when it has no uploaded image (PUB-003; shared with the /it home grid by PUB-025).
const categoryVisuals: Record<string, { accent: string; mark: string }> = {
  "Software Development": { accent: "#0878d1", mark: "</>" },
  Data: { accent: "#6d4bd3", mark: "01" },
  SAP: { accent: "#007f72", mark: "SAP" },
  Cloud: { accent: "#15865e", mark: "CLD" },
  "Artificial Intelligence": { accent: "#8450cc", mark: "AI" },
  "Cyber Security": { accent: "#d05b3f", mark: "SEC" },
  DevOps: { accent: "#26708e", mark: "OPS" },
};

export function programVisual(category: string) {
  return categoryVisuals[category] ?? { accent: "#0755b9", mark: "EDU" };
}
