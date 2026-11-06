import { alphaTab } from "@coderline/alphatab-vite";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  // alphaTab: копирует шрифт нот (Bravura) и SoundFont гитары, настраивает воркеры синтезатора.
  plugins: [react(), tailwindcss(), alphaTab()],
  server: {
    port: 5173,
    // В разработке API запущен отдельно (python -m fretlines_api) — проксируем запросы к нему.
    proxy: { "/api": "http://127.0.0.1:8080" },
  },
  build: {
    chunkSizeWarningLimit: 2500,
  },
});
