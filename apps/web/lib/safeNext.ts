// AGN-008 QA8-07: the login `next` is only ever a same-origin relative path (path + query + hash). Anything else -- `//host`,
// `/\host`, an absolute or scheme URL, control characters -- is refused, so the login page cannot be used as an open redirect.
const BASE = "http://next.invalid";

export function safeNextPath(value: string | null | undefined): string | null {
  if (!value || !value.startsWith("/") || value.startsWith("//") || /[\\\u0000-\u001f\u007f]/.test(value)) return null;
  let url: URL;
  try {
    url = new URL(value, BASE);
  } catch {
    return null;
  }
  if (url.origin !== BASE) return null;
  return `${url.pathname}${url.search}${url.hash}`;
}
