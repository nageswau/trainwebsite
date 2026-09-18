// A control that was disabled while busy loses keyboard focus in most browsers; put it back once
// the request ends so keyboard and screen-reader users keep their place.
export function refocus(id: string): void {
  requestAnimationFrame(() => document.getElementById(id)?.focus());
}
