/** Actual Next.js UI in Chromium, with API responses intercepted by the tests. */
module.exports = {
  testDir: "./e2e",
  timeout: 45000,
  retries: 0,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:3000", headless: true, trace: "retain-on-failure" },
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
};
