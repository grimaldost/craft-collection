// opencode shell: translates one execute.before event into a neutral event, asks the kit CLI for a
// verdict and throws on deny. It holds no policy and fails closed.
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const LOOKUP_MS = 1000;
const MAX_OUTPUT = 1024 * 1024;
const KILL_WAIT_MS = 1000;

const readConfig = () => {
  const c = JSON.parse(readFileSync(join(HERE, "shell_config.json"), "utf8"));
  const argvOk = Array.isArray(c?.cli_argv) && c.cli_argv.length > 0 && c.cli_argv.every((a) => typeof a === "string");
  const timeoutOk = c?.timeout_s === undefined || (Number.isFinite(c.timeout_s) && c.timeout_s > 0);
  if (c?.kit_shell_config !== 1 || !argvOk || !timeoutOk || typeof c.harness_version !== "string") {
    throw new Error("shell_config.json is malformed");
  }
  return c;
};

// Ends the CLI's tree and releases the host's hold on its pipes. The promise settles once the killer has
// exited, or after KILL_WAIT_MS: a host that tears its tree down as soon as this plugin settles would take
// a killer still at work with it. The killer's exit code is never read.
const kill = (child) =>
  new Promise((done) => {
    const wait = setTimeout(done, KILL_WAIT_MS);
    const over = () => (clearTimeout(wait), done());
    for (const stream of [child.stdin, child.stdout, child.stderr]) stream?.destroy();
    try {
      if (process.platform !== "win32") return over(process.kill(-child.pid, "SIGKILL"));
      const root = process.env.SystemRoot || "C:\\Windows";
      const args = ["/PID", String(child.pid), "/T", "/F"];
      const killer = spawn(root + "\\System32\\taskkill.exe", args, { stdio: "ignore", windowsHide: true });
      killer.on("error", over).on("exit", over).unref();
    } catch {
      over();
    }
  });

const runCli = (argv, text, ms) =>
  new Promise((done, fail) => {
    let child;
    let settled = false;
    const chunks = [];
    let size = 0;
    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      fn(value);
    };
    let stopping = false;
    const stop = (why) => {
      if (stopping) return;
      stopping = true;
      (child ? kill(child) : Promise.resolve()).then(() => finish(fail, new Error(why)));
    };
    const timer = setTimeout(() => stop("timed out"), Math.max(ms, 0));
    try {
      child = spawn(argv[0], argv.slice(1), {
        shell: false,
        windowsHide: true,
        detached: process.platform !== "win32",
        stdio: ["pipe", "pipe", "pipe"],
      });
    } catch (error) {
      return finish(fail, error);
    }
    child.on("error", (error) => finish(fail, error));
    child.stderr.resume();
    child.stdout.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_OUTPUT) return stop("output too large");
      chunks.push(chunk);
    });
    child.on("close", (code) => {
      if (stopping) return;
      finish(code === 0 ? done : fail, code === 0 ? Buffer.concat(chunks).toString("utf8") : new Error(`exit ${code}`));
    });
    child.stdin.on("error", () => {});
    child.stdin.end(text);
  });

// The session lookup gets at most LOOKUP_MS; a late result is ignored.
const lookup = (ctx, sessionID, ms) =>
  new Promise((done) => {
    const timer = setTimeout(() => done(null), ms);
    const settle = (info) => {
      clearTimeout(timer);
      done(info !== null && typeof info === "object" ? info : null);
    };
    Promise.resolve()
      .then(() => ctx.session.get({ sessionID }))
      .then(settle, () => settle(null));
  });

const mapAct = (ctx, e) => {
  const input = e.input ?? {};
  const act = { kind: "other", command: null, paths: [], command_obs: "not_applicable", paths_obs: "not_applicable" };
  if (e.tool === "shell") {
    return { ...act, kind: "shell", command: typeof input.command === "string" ? input.command : "", command_obs: "observed" };
  }
  if (e.tool === "write" || e.tool === "edit") {
    const ok = typeof input.path === "string";
    return { ...act, kind: "file_write", paths: ok ? [resolve(ctx.location.directory, input.path)] : [], paths_obs: ok ? "observed" : "unavailable" };
  }
  if (e.tool === "patch") return { ...act, kind: "file_write", paths_obs: "unavailable" };
  return act;
};

const judge = async (ctx, e, started) => {
  if (typeof e?.tool !== "string" || typeof e.sessionID !== "string") throw new Error("unreadable event");
  const config = readConfig();
  const deadline = (config.timeout_s ?? 3) * 1000;
  const sha = createHash("sha256").update(JSON.stringify(e), "utf8").digest("hex");
  const sessionID = e.sessionID;
  const info = await lookup(ctx, sessionID, Math.min(LOOKUP_MS, deadline));
  const parent = typeof info?.parentID === "string" && info.parentID !== "" ? info.parentID : null;
  const known = info !== null;
  const act = mapAct(ctx, e);
  const event = {
    kit_event: 1,
    run_id: process.env.KIT_RUN_ID || null,
    harness: { name: "opencode", version: config.harness_version },
    session: { id: sessionID, parent_id: parent, root_id: known && !parent ? sessionID : null },
    origin: parent ? "child" : "unknown",
    observation: {
      session: "observed",
      parent: known ? "observed" : "unavailable",
      root: known && !parent ? "observed" : "unavailable",
      origin: parent ? "observed" : "unavailable",
      command: act.command_obs,
      paths: act.paths_obs,
    },
    act: { kind: act.kind, command: act.command, argv: null, paths: act.paths, cwd: ctx.location.directory, payload_sha256: sha },
  };
  // JSON escapes keep the text sent to the CLI ASCII, whatever its console encoding.
  const text = JSON.stringify(event).replace(/[\u007f-\uffff]/g, (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
  const output = await runCli(config.cli_argv, text, deadline - (Date.now() - started));
  const verdict = JSON.parse(output.trim());
  if (verdict?.kit_verdict !== 1 || (verdict.effect !== "allow" && verdict.effect !== "deny")) {
    throw new Error("the CLI printed no verdict");
  }
  return verdict;
};

const describe = (error) => String(error?.message ?? error).replace(/[^\x20-\x7e]/g, "?").slice(0, 200);

const handler = async (ctx, e) => {
  const started = Date.now();
  let verdict;
  try {
    verdict = await judge(ctx, e, started);
  } catch (error) {
    throw new Error("kit could not judge: " + describe(error));
  }
  if (verdict.effect === "deny") throw new Error(String(verdict.reason || "denied by the kit policy"));
};

export default {
  id: "harness-kit",
  async setup(ctx) {
    await ctx.tool.hook("execute.before", (e) => handler(ctx, e));
  },
};
