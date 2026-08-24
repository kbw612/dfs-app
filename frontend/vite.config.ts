import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Runs as its own dev server (default port 5173), separate from the
// FastAPI backend (port 8000) -- see ../app/main.py for the CORS setup
// that allows this origin to call the API directly.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
  // __BUILD_TIME__ is baked into the bundle at build/dev-start time (see
  // src/version.ts, which reads it) -- shown in the header so it's obvious
  // from the running page itself whether you're looking at a freshly built
  // bundle or a stale cached one, without having to guess from a manually
  // maintained number alone.
  define: {
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },
});
