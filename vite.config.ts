import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Permite abrir o servidor de desenvolvimento por um túnel do ngrok (demonstrações).
    allowedHosts: [".ngrok-free.app", ".ngrok-free.dev", ".ngrok.app", ".ngrok.dev"],
    // Em desenvolvimento, /api vai para o backend FastAPI (backend/).
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
