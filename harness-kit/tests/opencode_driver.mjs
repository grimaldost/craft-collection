// Test driver: loads the opencode shell under Node with a fake host context.
// Reads one JSON spec on stdin, prints one JSON line with the outcome of one execute.before call.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const spec = JSON.parse(readFileSync(0, "utf8"));
const mod = await import(pathToFileURL(spec.shell).href);
const hooks = {};
const gets = [];
const ctx = {
  location: { directory: spec.directory },
  session: {
    get: async (arg) => {
      gets.push(arg);
      if (spec.session === "throw") throw new Error("lookup failed");
      if (spec.session === "hang") return new Promise(() => {});
      return spec.session === "parent" ? { id: arg.sessionID, parentID: "parent-1" } : { id: arg.sessionID };
    },
  },
  tool: {
    hook: async (name, fn) => {
      hooks[name] = fn;
    },
  },
};
await mod.default.setup(ctx);
const started = Date.now();
let threw = false;
let message = null;
try {
  await hooks["execute.before"](spec.event);
} catch (error) {
  threw = true;
  message = String(error.message);
}
console.log(
  JSON.stringify({
    id: mod.default.id,
    hooks: Object.keys(hooks),
    threw,
    message,
    elapsed_ms: Date.now() - started,
    gets,
  }),
);
