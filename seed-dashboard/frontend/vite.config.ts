import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy /api to the FastAPI backend so the frontend calls same-origin in dev.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5273,
    proxy: { "/api": "http://localhost:8000" },
  },
});
