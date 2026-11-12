import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  define: {
    CESIUM_BASE_URL: JSON.stringify("/cesium"),
  },
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  optimizeDeps: {
    include: ["cesium", "mersenne-twister"],
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      // Harmonized-record snapshot API (backend/routers/snapshot.py)
      "/meta": "http://127.0.0.1:8000",
      "/fires": "http://127.0.0.1:8000",
      "/events/": "http://127.0.0.1:8000",
      "/detections": "http://127.0.0.1:8000",
    },
  },
});
