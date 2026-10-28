# Vben Admin source provenance

Official repository: https://github.com/vbenjs/vue-vben-admin
Commit: 8c87902658b8b8aa8703cf371323bca1273d3a7c
Root upstream version 5.7.0; framework workspace packages identify as 5.8.0.
MIT license retained in LICENSE. Original root manifest retained as UPSTREAM.package.json.

MOSS uses the actual VbenAdminLayout from @vben-core/layout-ui and VbenButton from @vben-core/shadcn-ui, with official design tokens. The workspace manifest limits installation to required Vben core packages and apps/moss; upstream demos remain source-only. No mock server, mock login, or frontend auth token is used.

Install: pnpm install --frozen-lockfile --ignore-scripts
Run: pnpm dev
Build: pnpm build
Typecheck: pnpm typecheck
Test: pnpm test
