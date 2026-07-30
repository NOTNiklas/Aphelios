import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // Tauri erwartet einen festen Port; im Browser ist er ebenfalls praktisch.
  server: {
    port: 5173,
    strictPort: false,
    host: true,
  },
  clearScreen: false,
});
