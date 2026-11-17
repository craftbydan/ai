import { defineConfig } from "@playwright/test";

// Set PW_CHROMIUM_PATH to use a pre-installed Chromium instead of the bundled one.
const executablePath = process.env.PW_CHROMIUM_PATH;

// E2E_PHASE=dev (default): API runs with DEV_USER=1 BILLING=off; every flow except auth.
// E2E_PHASE=auth: API runs with DEV_USER=0 (real accounts only); only the signup/login/logout flow.
const authPhase = process.env.E2E_PHASE === "auth";

export default defineConfig({
  testDir: "./e2e",
  testMatch: authPhase ? "auth.spec.ts" : undefined,
  testIgnore: authPhase ? undefined : "auth.spec.ts",
  // One dev user and one hand are shared by every flow, so run them in order.
  workers: 1,
  fullyParallel: false,
  timeout: 60_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL: "http://localhost:3000",
    launchOptions: executablePath ? { executablePath } : {},
    acceptDownloads: true,
  },
});
