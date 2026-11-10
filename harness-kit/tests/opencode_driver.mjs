// Test driver: loads the opencode shell under Node with a fake host context.
// Reads one JSON spec on stdin, prints one JSON line with the outcome of one execute.before call.
import cp from "node:child_process";
import { EventEmitter } from "node:events";
import { readFileSync } from "node:fs";
import { syncBuiltinESMExports } from "node:module";
import { pathToFileURL } from "node:url";

const spec = JSON.parse(readFileSync(0, "utf8"));
let killerDone = false;
if (spec.killerDelayMs) {
  // A slow killer: the real taskkill starts killerDelayMs late, and its exit is reported when it ends.
  const real = cp.spawn;
  cp.spawn = (cmd, args, opts) => {
    if (!/taskkill\.exe$/i.test(cmd)) return real(cmd, args, opts);
    const fake = new EventEmitter();
    fake.unref = () => fake;
    setTimeout(() => {
      real(cmd, args, opts).on("exit", () => {
        killerDone = true;
        fake.emit("exit", 0);
      });
    }, spec.killerDelayMs);
    return fake;
  };
  syncBuiltinESMExports();
}
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
    killer_done: killerDone,
    gets,
  }),
);
