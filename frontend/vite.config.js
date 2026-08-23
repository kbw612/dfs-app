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
});
