const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const testDir = fs.mkdtempSync(path.join(os.tmpdir(), "proofgraph-e2e-"));
const databasePath = path.join(testDir, "disputes.db");
const uploadPath = path.join(testDir, "uploads");

module.exports = {
  testDir: "./e2e",
  timeout: 45000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:3001",
    headless: true,
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `${process.env.CI ? "python" : "../api/.venv/bin/python"} -m uvicorn app.main:app --app-dir ../api --host 127.0.0.1 --port 8001`,
      url: "http://127.0.0.1:8001/api/v1/health",
      env: {
        ...process.env,
        DATABASE_URL: `sqlite:///${databasePath}`,
        UPLOAD_DIR: uploadPath,
      },
      reuseExistingServer: false,
      timeout: 120000,
    },
    {
      command: "npm run dev -- -p 3001",
      url: "http://127.0.0.1:3001",
      env: {
        ...process.env,
        PROOFGRAPH_API_PORT: "8001",
        PROOFGRAPH_E2E: "1",
      },
      reuseExistingServer: false,
      timeout: 120000,
    },
  ],
};
