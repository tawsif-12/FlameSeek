import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  define: {
    CESIUM_BASE_URL: JSON.stringify("/cesium"),
  },
  plugins: [react()],
  optimizeDeps: {
    include: ["cesium", "mersenne-twister"],
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8003",
      "/data-sources": "http://127.0.0.1:8003",
    },
  },
});
