/** Add the minimal Cloudflare Worker entrypoint required by Sites hosting. */

import { copyFile, mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const serverDirectory = resolve("dist/server");
const serverPath = resolve(serverDirectory, "index.js");
const workerSource = `export default {
  async fetch(request, env) {
    return env.ASSETS.fetch(request);
  },
};
`;

await mkdir(serverDirectory, { recursive: true });
await writeFile(serverPath, workerSource, "utf8");
await copyFile(resolve("public/og.png"), resolve("dist/og.png"));
