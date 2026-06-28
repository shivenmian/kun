import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Vite dev server. The `/api` proxy points at the FastAPI backend (CONTRACT §5).
// The static sample replay path does NOT use the proxy — it loads
// /sample.events.jsonl directly from public/, so the cockpit works fully offline.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        // Backend paths are bare (e.g. /missions/{id}/stream). The frontend calls
        // /api/missions/... and we strip the /api prefix here.
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
