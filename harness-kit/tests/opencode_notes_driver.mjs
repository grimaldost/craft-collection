// Test driver: loads the opencode shell under Node with a fake host context and calls its hooks in turn.
// Reads one JSON spec on stdin and prints one JSON line: the hooks registered, the session lookups made and,
// for each call, whether the hook threw and how long it took.
//
// spec.sessions maps a session id to {parentID?, delayMs?} (found, after delayMs), "throw" (the lookup throws), "hang" (it never
// resolves) or "nothing" (it returns no object); an id not in the map also returns no object.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const spec = JSON.parse(readFileSync(0, "utf8"));
const mod = await import(pathToFileURL(spec.shell).href);
const hooks = {};
const registered = { tool: [], session: [] };
const gets = [];
const ctx = {
  location: { directory: spec.directory },
  session: {
    get: async (arg) => {
      gets.push(arg.sessionID);
      const found = spec.sessions[arg.sessionID];
      if (found === "throw") throw new Error("lookup failed");
      if (found === "hang") return new Promise(() => {});
      if (found === undefined || found === "nothing") return null;
      const { delayMs, ...info } = found;
      if (delayMs) await new Promise((done) => setTimeout(done, delayMs));
      return { id: arg.sessionID, ...info };
    },
    hook: async (name, fn) => {
      registered.session.push(name);
      hooks["session:" + name] = fn;
    },
  },
  tool: {
    hook: async (name, fn) => {
      registered.tool.push(name);
      hooks["tool:" + name] = fn;
    },
  },
};
await mod.default.setup(ctx);
const results = [];
for (const call of spec.calls) {
  const fn = hooks[call.hook];
  const started = Date.now();
  let threw = false;
  let message = null;
  let value;
  if (fn === undefined) {
    results.push({ registered: false });
    continue;
  }
  try {
    value = await fn(call.arg);
  } catch (error) {
    threw = true;
    message = String(error?.message ?? error);
  }
  results.push({ registered: true, threw, message, value: value ?? null, elapsed_ms: Date.now() - started });
}
console.log(JSON.stringify({ registered, gets, results }));
