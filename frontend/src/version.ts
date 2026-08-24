// Shown in the header (see App.tsx) so a stale cached bundle is obvious
// from the running page itself instead of having to guess -- this is what
// came up troubleshooting the Ownership Leverage tab not appearing after a
// browser held onto an old bundle.
//
// FRONTEND_VERSION is bumped by hand for notable changes (new tab, new
// feature) -- keep it in sync with package.json's "version" field. It's
// meant to answer "did my rebuild actually ship this feature." BUILD_TIME
// is filled in automatically by vite.config.ts's `define` at build/dev-start
// time and needs no maintenance -- it's meant to answer "am I looking at a
// stale cached bundle," since it changes on every single build even when
// FRONTEND_VERSION doesn't.
export const FRONTEND_VERSION = "0.2.0";
export const BUILD_TIME = __BUILD_TIME__;
