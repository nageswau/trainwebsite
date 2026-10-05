// ENH-016 QA-016-11: "1 teacher", "3 students" -- a count with the right form of its noun.
export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count.toLocaleString("en-IN")} ${count === 1 ? one : many}`;
}
