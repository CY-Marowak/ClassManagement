import { spawn } from "node:child_process";
import { resolve } from "node:path";

const python =
  process.platform === "win32"
    ? ".venv/Scripts/python.exe"
    : ".venv/bin/python";
const child = spawn(
  resolve(python),
  ["backend/manage.py", "runserver", "127.0.0.1:8000", "--noreload"],
  {
    env: { ...process.env, CM_DEBUG: "1" },
    stdio: "inherit",
    windowsHide: true,
  },
);
child.on("exit", (code) => process.exit(code ?? 1));
for (const signal of ["SIGINT", "SIGTERM"])
  process.on(signal, () => child.kill());
