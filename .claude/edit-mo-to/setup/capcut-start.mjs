// Launcher for the CapCut MCP server: starts the VectCutAPI backend on
// port 9001 in the background if it isn't already running, then runs the
// MCP server itself over stdio.
import { spawn } from "node:child_process";
import net from "node:net";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const vectcutDir = path.join(root, "VectCutAPI");
const python = path.join(vectcutDir, ".venv", "Scripts", "python.exe");
const PORT = 9001;

function isListening(port) {
  return new Promise((resolve) => {
    const sock = net.connect({ port, host: "127.0.0.1" });
    sock.once("connect", () => { sock.destroy(); resolve(true); });
    sock.once("error", () => resolve(false));
    sock.setTimeout(500, () => { sock.destroy(); resolve(false); });
  });
}

if (!(await isListening(PORT))) {
  // stdio must be ignored: the MCP protocol uses this process's stdout.
  const child = spawn(python, ["capcut_server.py"], {
    cwd: vectcutDir,
    detached: true,
    windowsHide: true,
    stdio: "ignore",
  });
  child.unref();
  for (let i = 0; i < 40 && !(await isListening(PORT)); i++) {
    await new Promise((r) => setTimeout(r, 250));
  }
}

await import(pathToFileURL(path.join(root, "capcut-mcp-server-extended", "dist", "index.js")).href);
