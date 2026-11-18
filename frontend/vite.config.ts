import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: {
        name: "FarmMarket",
        short_name: "FarmMarket",
        description: "Fair market for farmers and buyers — কৃষকের ন্যায্য বাজার",
        theme_color: "#0C3B2E",
        background_color: "#FBF7EF",
        display: "standalone",
        start_url: "/",
        scope: "/",
        icons: [
          { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,ico}"],
        navigateFallback: "/index.html",
        // A direct navigation to an API or upload URL (e.g. a friend opening
        // a shared listing image) must reach the backend, not be answered
        // with the cached SPA shell by the service worker.
        navigateFallbackDenylist: [/^\/api\//, /^\/uploads\//],
      },
    }),
  ],
  server: {
    port: 5173,
    // Vite 6 rejects requests whose Host it does not know ("Blocked
    // request. This host is not allowed"). The devtunnel relay rewrites
    // Host to localhost by default, so a VS Code tunnel works without
    // this — but any tunnel that preserves the host (ngrok, cloudflared,
    // or `devtunnel update --host-header unchanged`) would be blocked.
    // Allow devtunnel subdomains up front so sharing the dev server
    // never fails on the host check. Dev-only; no production effect.
    allowedHosts: [".devtunnels.ms"],
    proxy: {
      "/api": "http://127.0.0.1:8000",
      // Uploaded listing images are served by the backend at /uploads/*.
      // Without this the dev server answers them itself (SPA fallback HTML),
      // so every uploaded photo is broken in dev — locally and for anyone
      // on a shared devtunnel link.
      "/uploads": "http://127.0.0.1:8000",
    },
  },
  preview: {
    port: 4173,
  },
});
