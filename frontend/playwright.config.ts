import { defineConfig } from "@playwright/test";

/**
 * Targets the already-running docker-compose stack (frontend on :3000,
 * backend on :8000) rather than starting its own dev server - this suite
 * verifies the real built containers, not a separate ad-hoc process.
 * globalSetup seeds a dedicated e2e organization/station/user through the
 * API directly (not the UI) so each test run starts from known data.
 */
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  use: {
    // Overridable via E2E_BASE_URL for a machine where :3000 is already
    // taken by something else (e.g. another project's dev server) -
    // docker-compose.yml's own frontend port mapping is the source of
    // truth for what this should normally be.
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
