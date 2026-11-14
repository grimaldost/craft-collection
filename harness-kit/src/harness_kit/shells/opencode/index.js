// opencode shell: translates one execute.before event into a neutral event, asks the kit CLI for a
// verdict and throws on deny. It holds no policy and fails closed. With note_config.json beside it, it
// also sends the kit CLI a note for each typed prompt and each finished shell call; a note never denies.
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const LOOKUP_MS = 1000;
const MAX_OUTPUT = 1024 * 1024;
const KILL_WAIT_MS = 1000;
const [MAX_PARENTS, MAX_TEXT, MAX_NOTE_OUTPUT] = [4, 20000, 65536];

const readConfig = () => {
  const c = JSON.parse(readFileSync(join(HERE, "shell_config.json"), "utf8"));
  const argvOk = Array.isArray(c?.cli_argv) && c.cli_argv.length > 0 && c.cli_argv.every((a) => typeof a === "string");
  const timeoutOk = c?.timeout_s === undefined || (Number.isFinite(c.timeout_s) && c.timeout_s > 0);
  if (c?.kit_shell_config !== 1 || !argvOk || !timeoutOk || typeof c.harness_version !== "string") {
    throw new Error("shell_config.json is malformed");
  }
  return c;
};

// The note configuration, or null when it is absent or malformed: then no note hook is registered.
const readNoteConfig = () => {
  try {
    const c = JSON.parse(readFileSync(join(HERE, "note_config.json"), "utf8"));
    const argvOk = Array.isArray(c?.note_argv) && c.note_argv.length > 0 && c.note_argv.every((a) => typeof a === "string");
    const recordsOk = Array.isArray(c?.records) && c.records.every((r) => r === "prompt" || r === "outcome");
    return c?.kit_note_config === 1 && argvOk && Number.isFinite(c.timeout_s) && c.timeout_s > 0 && recordsOk ? c : null;
  } catch {
    return null;
  }
};

// JSON escapes keep the text sent to the CLI ASCII, whatever its console encoding.
const ascii = (doc) => JSON.stringify(doc).replace(/[\u007f-\uffff]/g, (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));

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

const parentOf = (info) => (typeof info?.parentID === "string" && info.parentID !== "" ? info.parentID : null);

// The session's place in its tree: one lookup or, with notes on, a walk to the root, at most MAX_PARENTS
// lookups beyond the first, all inside the first one's time, which ends at `until`.
const locate = async (ctx, sessionID, until, walk) => {
  const info = await lookup(ctx, sessionID, until - Date.now());
  const parent = parentOf(info);
  let root = info !== null && !parent ? sessionID : null;
  const seen = new Set([sessionID]);
  for (let id = parent, n = 0; walk && id !== null && n < MAX_PARENTS && !seen.has(id) && Date.now() < until; n++) {
    seen.add(id);
    const above = await lookup(ctx, id, until - Date.now());
    if (above === null) break;
    if (parentOf(above) === null) root = id;
    id = parentOf(above);
  }
  const seenIf = (ok) => (ok ? "observed" : "unavailable");
  return {
    known: info !== null,
    session: { id: sessionID, parent_id: parent, root_id: root },
    origin: parent ? "child" : "unknown",
    observation: { session: "observed", parent: seenIf(info !== null), root: seenIf(root !== null), origin: seenIf(parent !== null) },
  };
};

// What an event and a note share: the run, the harness, the session's place and the observation.
const frame = (config, place, act) => ({
  run_id: process.env.KIT_RUN_ID || null,
  harness: { name: "opencode", version: config.harness_version },
  session: place.session,
  origin: place.origin,
  observation: { ...place.observation, command: act.command_obs, paths: act.paths_obs },
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

const neutralAct = (ctx, e, act) => {
  const sha = createHash("sha256").update(JSON.stringify(e), "utf8").digest("hex");
  return { kind: act.kind, command: act.command, argv: null, paths: act.paths, cwd: ctx.location.directory, payload_sha256: sha };
};

const judge = async (ctx, e, started, walk) => {
  if (typeof e?.tool !== "string" || typeof e.sessionID !== "string") throw new Error("unreadable event");
  const config = readConfig();
  const deadline = (config.timeout_s ?? 3) * 1000;
  const place = await locate(ctx, e.sessionID, started + Math.min(LOOKUP_MS, deadline), walk);
  const act = mapAct(ctx, e);
  const event = { kit_event: 1, ...frame(config, place, act), act: neutralAct(ctx, e, act) };
  const output = await runCli(config.cli_argv, ascii(event), deadline - (Date.now() - started));
  const verdict = JSON.parse(output.trim());
  if (verdict?.kit_verdict !== 1 || (verdict.effect !== "allow" && verdict.effect !== "deny")) {
    throw new Error("the CLI printed no verdict");
  }
  return verdict;
};

const describe = (error) => String(error?.message ?? error).replace(/[^\x20-\x7e]/g, "?").slice(0, 200);

const handler = async (ctx, e, walk) => {
  const started = Date.now();
  let verdict;
  try {
    verdict = await judge(ctx, e, started, walk);
  } catch (error) {
    throw new Error("kit could not judge: " + describe(error));
  }
  if (verdict.effect === "deny") throw new Error(String(verdict.reason || "denied by the kit policy"));
};

// A typed prompt's note: one enclosing pair of literal double quotes, which opencode adds, is removed,
// then the first MAX_TEXT code points are kept. Null when there is no text.
const promptBody = (e) => {
  if (typeof e?.prompt?.text !== "string") return null;
  let points = Array.from(e.prompt.text);
  if (points.length >= 2 && points[0] === '"' && points[points.length - 1] === '"') points = points.slice(1, -1);
  return { kind: "prompt", text: points.slice(0, MAX_TEXT).join(""), truncated: points.length > MAX_TEXT };
};

const outcomeStatus = (e) => {
  const out = e.result?.output;
  if (e.status === "error") return "failed";
  if (e.result?.metadata?.status === "running" || out?.status === "running") return "background";
  if (out?.exit === 0) return "completed";
  return typeof out?.exit === "number" ? "failed" : "unknown";
};

// A finished shell call's note: its status and, when it completed, its last MAX_NOTE_OUTPUT code points.
const outcomeBody = (ctx, e) => {
  const status = outcomeStatus(e);
  const text = e.result?.output?.output;
  const points = status === "completed" && typeof text === "string" ? Array.from(text) : null;
  return {
    kind: "outcome",
    act: neutralAct(ctx, e, mapAct(ctx, e)),
    status,
    output: points === null ? null : points.slice(-MAX_NOTE_OUTPUT).join(""),
    truncated: points !== null && (points.length > MAX_NOTE_OUTPUT || e.result.output.truncated === true),
  };
};

// Sends one note through the judgement's own runCli and resolves whatever happens: a note never denies,
// never throws and writes nothing to the host. The CLI's output and exit status are not read.
const noteHandler = async (ctx, e, notes, kind) => {
  const started = Date.now();
  try {
    if (typeof e?.sessionID !== "string" || (kind === "outcome" && e.tool !== "shell")) return;
    const deadline = notes.timeout_s * 1000;
    const config = readConfig();
    const body = kind === "prompt" ? promptBody(e) : outcomeBody(ctx, e);
    if (body === null) return;
    const place = await locate(ctx, e.sessionID, started + Math.min(LOOKUP_MS, deadline), true);
    // Without the first lookup's answer a child's prompt would arrive as `unknown`: no prompt note then.
    if (kind === "prompt" && !place.known) return;
    const act = kind === "outcome" ? mapAct(ctx, e) : { command_obs: "not_applicable", paths_obs: "not_applicable" };
    const note = { kit_note: 1, ...frame(config, place, act), note: body };
    await runCli(notes.note_argv, ascii(note), deadline - (Date.now() - started));
  } catch {
    // The note is lost and nothing is blocked.
  }
};

export default {
  id: "harness-kit",
  async setup(ctx) {
    const notes = readNoteConfig();
    await ctx.tool.hook("execute.before", (e) => handler(ctx, e, notes !== null));
    if (notes?.records.includes("prompt")) await ctx.session.hook("prompt", (e) => noteHandler(ctx, e, notes, "prompt"));
    if (notes?.records.includes("outcome")) await ctx.tool.hook("execute.after", (e) => noteHandler(ctx, e, notes, "outcome"));
  },
};
