#!/usr/bin/env node
import { createHash, randomBytes } from "node:crypto";
import { chmod, mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { spawn, spawnSync } from "node:child_process";

const envPath = join(homedir(), ".openclaw", ".env");
let savedEnv = "";
try { savedEnv = await readFile(envPath, "utf8"); } catch {}
function savedValue(key) {
  const prefix = key + "=";
  const line = savedEnv.split(/\r?\n/).find((value) => value.startsWith(prefix));
  return line ? line.slice(prefix.length).trim() : "";
}
const savedCa = savedValue("NODE_EXTRA_CA_CERTS");
if (!process.env.NODE_EXTRA_CA_CERTS && savedCa && !process.env.RESONO_VAULT_PAIR_REEXEC) {
  const child = spawnSync(process.execPath, process.argv.slice(1), {
    stdio: "inherit", env: { ...process.env, NODE_EXTRA_CA_CERTS: savedCa, RESONO_VAULT_PAIR_REEXEC: "1" },
  });
  process.exit(child.status ?? 1);
}
const baseUrl = String(process.env.RESONO_VAULT_MEMORY_URL || savedValue("RESONO_VAULT_MEMORY_URL") || "https://127.0.0.1:8765").replace(/\/+$/, "");
const credential = randomBytes(32).toString("base64url");
const pollToken = randomBytes(32).toString("base64url");

async function post(path, payload, runtimeCredential = "") {
  const headers = { "content-type": "application/json" };
  if (runtimeCredential) headers.authorization = `Bearer ${runtimeCredential}`;
  const response = await fetch(baseUrl + path, {
    method: "POST", headers, body: JSON.stringify(payload),
  });
  const value = await response.json();
  if (!response.ok) throw new Error(value?.error?.message || `Vault returned HTTP ${response.status}`);
  return value;
}

async function saveEnv(path) {
  const key = "RESONO_VAULT_MEMORY_CREDENTIAL";
  let lines = [];
  try { lines = (await readFile(path, "utf8")).split(/\r?\n/); } catch {}
  lines = lines.filter((line) => line && !line.startsWith(key + "="));
  lines.push(`${key}=${credential}`);
  await mkdir(dirname(path), { recursive: true });
  const temporary = path + ".tmp";
  await writeFile(temporary, lines.join("\n") + "\n", { mode: 0o600 });
  await chmod(temporary, 0o600);
  await rename(temporary, path);
}

async function readCredential(path) {
  try {
    const line = (await readFile(path, "utf8")).split(/\r?\n/)
      .find((value) => value.startsWith("RESONO_VAULT_MEMORY_CREDENTIAL="));
    return line ? line.slice(line.indexOf("=") + 1).trim() : "";
  } catch { return ""; }
}

async function removeCredential(path) {
  let lines = [];
  try { lines = (await readFile(path, "utf8")).split(/\r?\n/); } catch { return; }
  lines = lines.filter((line) => line && !line.startsWith("RESONO_VAULT_MEMORY_CREDENTIAL="));
  const temporary = path + ".tmp";
  await writeFile(temporary, lines.join("\n") + (lines.length ? "\n" : ""), { mode: 0o600 });
  await rename(temporary, path);
}

if (process.argv.includes("--disconnect")) {
  const runtimeCredential = process.env.RESONO_VAULT_MEMORY_CREDENTIAL || await readCredential(envPath);
  if (runtimeCredential && !process.argv.includes("--local-only")) {
    await post("/external-memory/v1/disconnect", { requestId: randomBytes(16).toString("hex") }, runtimeCredential);
  }
  await removeCredential(envPath);
  spawnSync("openclaw", ["config", "set", "plugins.slots.memory", "memory-core"], { stdio: "inherit" });
  spawnSync("openclaw", ["plugins", "disable", "resono-vault-memory"], { stdio: "inherit" });
  console.log("OpenClaw is disconnected from Vault Memory and memory-core is restored. Restart OpenClaw.");
  process.exit(0);
}

const started = await post("/external-memory/pairing/start", {
  displayName: "OpenClaw", adapterKind: "openclaw",
  grants: ["search", "propose", "correct", "forget"], pollToken,
  runtimeTokenHash: createHash("sha256").update(credential).digest("hex"),
});
const approvalUrl = `${baseUrl}/?memoryPairing=${encodeURIComponent(started.pairingCode)}`;
console.log(`Opening Vault to connect OpenClaw. Pairing code: ${started.pairingCode}`);
spawn(process.platform === "darwin" ? "open" : process.platform === "win32" ? "cmd" : "xdg-open",
  process.platform === "win32" ? ["/c", "start", "", approvalUrl] : [approvalUrl],
  { detached: true, stdio: "ignore" }).unref();
const deadline = Date.now() + 600_000;
while (Date.now() < deadline) {
  const result = await post("/external-memory/pairing/status", { pairingId: started.pairingId, pollToken });
  if (result.status === "approved") {
    await saveEnv(envPath);
    const patch = {
      plugins: {
        slots: { memory: "resono-vault-memory" },
        entries: {
          "resono-vault-memory": {
            enabled: true,
            config: {
              credential: "${RESONO_VAULT_MEMORY_CREDENTIAL}", baseUrl,
              autoCapture: true, autoRecall: true, startupMemory: true,
              dreaming: { enabled: false },
            },
            hooks: { allowConversationAccess: true },
          },
        },
      },
    };
    const configured = spawnSync("openclaw", ["config", "patch", "--stdin"], {
      input: JSON.stringify(patch), encoding: "utf8", stdio: ["pipe", "inherit", "inherit"],
    });
    if (configured.status !== 0) throw new Error("OpenClaw configuration could not be updated.");
    console.log("OpenClaw is connected to Vault Memory. Restart OpenClaw to load it.");
    process.exit(0);
  }
  if (result.status === "expired") break;
  await new Promise((resolve) => setTimeout(resolve, 2000));
}
throw new Error("Pairing expired before it was approved.");
