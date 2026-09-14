import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

const config = [
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts"] },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      // Downgraded from the next/typescript default of "error" to "warn": ~25
      // pre-existing `any` usages across app/**/page.tsx and a couple of
      // components predate ESLint being introduced in this foundation pass and
      // are out of scope for it (see docs/IMPLEMENTATION_PLAN.md Slice 10). At
      // "error" severity, Next's build-time lint step (`next build`) would hard
      // fail the production build on this pre-existing debt. Restore to "error"
      // once that cleanup lands.
      "@typescript-eslint/no-explicit-any": "warn",
    },
  },
];

export default config;
