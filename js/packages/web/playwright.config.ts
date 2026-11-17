// Browser tests of the graph editor against a running rasl (pnpm e2e; CI job "Web editor").
// rasl serves the built page (pnpm build first) and a copy of e2e/fixture.conf, which each
// test restores before it starts.
import { defineConfig } from "@playwright/test";

export const PORT = 18420;
export const CONFIG = "e2e/.run/rasl.conf";

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${PORT}`, trace: "off", viewport: { width: 1400, height: 860 } },
  webServer: {
    command: `mkdir -p e2e/.run && cp e2e/fixture.conf ${CONFIG} && uv run --project ../../.. rasl ${CONFIG} --api-port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/health`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
