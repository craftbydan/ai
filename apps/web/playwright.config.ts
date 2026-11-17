import { defineConfig } from "@playwright/test";

// Set PW_CHROMIUM_PATH to use a pre-installed Chromium instead of the bundled one.
const executablePath = process.env.PW_CHROMIUM_PATH;

export default defineConfig({
  testDir: "./e2e",
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
