/// <reference types="vitest" />
// The web UI is built into the Python package, which serves it at GET / (rasl.app.server.app).
// `pnpm dev` serves it with hot reload and forwards /graphql to a running rasl (RASL_API).
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const api = process.env.RASL_API ?? "http://127.0.0.1:8080";

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../../../src/rasl/app/ui",
    emptyOutDir: true,
    sourcemap: false,
    chunkSizeWarningLimit: 1600,
  },
  server: {
    proxy: { "/graphql": { target: api, ws: true } },
  },
  test: {
    environment: "node",
  },
});
