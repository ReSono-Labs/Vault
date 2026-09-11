import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  build: { outDir: "dist", rollupOptions: { input: path.resolve(__dirname, "browser-voice.html") } },
  server: { host: "127.0.0.1", port: 4174 },
  preview: { host: "127.0.0.1", port: 4174 },
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"] },
});
