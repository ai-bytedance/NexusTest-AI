# Frontend Placeholder

The frontend implementation will be added in a future milestone.

## Development Notes

- When adding or updating page components, ensure import statements match the exact case-sensitive file names. Linux-based build environments treat paths as case-sensitive, so mismatches will cause the build to fail.
- Prefer explicit module paths (for example `@/pages/ReportsPage.tsx`) when adding new imports so Vite can resolve them consistently in both local and containerized workflows.
- Keep the `@` path alias definitions in `vite.config.ts` and `tsconfig.json` synchronized whenever you adjust module resolution settings.
