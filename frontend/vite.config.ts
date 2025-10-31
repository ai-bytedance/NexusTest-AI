import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import monacoEditorPlugin from "vite-plugin-monaco-editor";
import path from "path";

const resolvedMonacoEditorPlugin =
  (monacoEditorPlugin as unknown as { default?: typeof monacoEditorPlugin }).default ??
  monacoEditorPlugin;

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    resolvedMonacoEditorPlugin({
      languageWorkers: ["editorWorkerService", "json", "typescript", "html", "css"],
    }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    host: "0.0.0.0",
  },
});
