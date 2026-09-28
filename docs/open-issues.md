# Open issues / known tech debt

Tracked, deliberately-deferred items. Not blocking — revisit when convenient.

## Frontend dev-tooling vulnerabilities (vite/vitest/esbuild)

**Status:** deferred, not urgent.

`npm audit` (no flags) reports 6 vulnerabilities (moderate/high/critical) in `vite`, `vitest`,
`esbuild`, and `electron-vite`. All are **devDependencies** — build tooling and the test runner,
not code shipped in the packaged Electron app. Confirmed with the same check CI already runs:

```
npm audit --omit=dev --audit-level=high
→ found 0 vulnerabilities
```

`.github/workflows/ci.yml`'s "Dependency vulnerability scan (npm audit)" step already uses
`--omit=dev --audit-level=high` for exactly this reason, so CI is unaffected.

The two underlying advisories only matter in scenarios that don't apply to end users of the built
app:
- esbuild (GHSA-67mh-4wv8-2f99): requires an attacker reaching your local `vite`/`electron-vite`
  **dev server** while `npm run dev` is running.
- @vitest/mocker (GHSA-82fw-gwwq-j7x9): only relevant while running the test suite locally.

**Fix available:** `npm audit fix --force` — but this bumps `vitest` 2→5 and `vite` 5→8, both
major versions, likely to require Vitest-config and electron-vite build-pipeline migration work.

**When to actually do this:** as a standalone maintenance PR, not bundled with feature work.
Bump `vite`/`vitest`/`electron-vite`/`esbuild` deliberately, then verify `npm run dev`,
`npm run build`, and the full test suite (`npm test`) still pass before merging.
