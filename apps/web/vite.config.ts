import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
      // The shared contract's generated types. Type-only: nothing from here ships in the bundle.
      "@schema": fileURLToPath(new URL("../../packages/analysis-schema/types/typescript", import.meta.url)),
    },
  },
  server: { port: 5173 },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
