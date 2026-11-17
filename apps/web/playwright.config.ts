import { defineConfig } from "@playwright/test";

// Set PW_CHROMIUM_PATH to use a pre-installed Chromium instead of the bundled one.
const executablePath = process.env.PW_CHROMIUM_PATH;

export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL: "http://localhost:3000",
    launchOptions: executablePath ? { executablePath } : {},
  },
});
