/** Actual Next.js UI in Chromium, with API responses intercepted by the tests. */
module.exports = {
  testDir: "./e2e",
  timeout: 45000,
  retries: 0,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:3000", headless: true, trace: "retain-on-failure" },
  webServer: [
    {
      command: "cd ../api && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/api/v1/health",
      env: { ...process.env, DATABASE_URL: "sqlite:////tmp/proofgraph-browser-test.db" },
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
    },
  ],
};
