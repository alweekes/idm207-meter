import { defineConfig } from "vitest/config";

export default defineConfig({
  base: "./",
  server: { fs: { allow: ["../.."] } }, // dev server may serve ../../reverse-engineering/capture.log for ?replay=
  test: { environment: "node" },
});
