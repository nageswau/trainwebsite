import { isValidElement, type ReactElement, type ReactNode } from "react";

// Helpers for asserting on what an async server component RETURNS (a React element tree) without rendering it: no component
// inside the tree is invoked, so its site header, footer and client components stay out of the unit under test.

type Props = Record<string, unknown> & { children?: ReactNode };

/** Every element in the tree, depth-first. */
export function elements(node: ReactNode, found: ReactElement<Props>[] = []): ReactElement<Props>[] {
  if (Array.isArray(node)) {
    node.forEach((child) => elements(child, found));
  } else if (isValidElement<Props>(node)) {
    found.push(node);
    elements(node.props.children, found);
  }
  return found;
}

/** The text a node would show, concatenated. */
export function text(node: ReactNode): string {
  if (Array.isArray(node)) return node.map(text).join("");
  if (isValidElement<Props>(node)) return text(node.props.children);
  return typeof node === "string" || typeof node === "number" ? String(node) : "";
}
