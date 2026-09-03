import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/aulas": "http://127.0.0.1:8000",
      "/alunos": "http://127.0.0.1:8000",
      "/turmas": "http://127.0.0.1:8000",
      "/professores": "http://127.0.0.1:8000",
      "/relatorios": "http://127.0.0.1:8000",
      "/token": "http://127.0.0.1:8000",
      "/reagendar": "http://127.0.0.1:8000",
    },
  },
});
