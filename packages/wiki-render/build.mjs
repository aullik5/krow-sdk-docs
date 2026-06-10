// 可选构建：为非打包器消费者产出 CJS + 压缩 ESM。
// markdown-it 由消费者注入（不打进 bundle），故 external。
// 用法：npm i -D esbuild@latest && npm run build
import { build } from "esbuild";

const common = {
  entryPoints: ["wiki-render.js"],
  bundle: true,
  platform: "browser",
  external: ["markdown-it"],
  logLevel: "info",
};

await build({ ...common, format: "cjs", outfile: "dist/wiki-render.cjs" });
await build({ ...common, format: "esm", minify: true, outfile: "dist/wiki-render.min.js" });

console.log("built dist/wiki-render.cjs + dist/wiki-render.min.js");
