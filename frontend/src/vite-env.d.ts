/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// Injected by vite.config.ts's `define` -- an ISO timestamp of when this
// bundle was built (or when the dev server started, for `npm run dev`).
declare const __BUILD_TIME__: string;
