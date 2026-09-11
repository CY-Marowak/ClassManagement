// Local development only: an actual PostgreSQL cluster, kept under .local/.
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync, unlinkSync } from "node:fs";
import { resolve, join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const local = join(root, ".local");
const data = join(local, "postgres");
const platform = process.platform === "win32" ? "windows" : process.platform;
const { postgres, initdb } = await import(
  `@embedded-postgres/${platform}-${process.arch}`
);
const pgCtl = join(
  dirname(postgres),
  process.platform === "win32" ? "pg_ctl.exe" : "pg_ctl",
);
const run = (file, args) => {
  const result = spawnSync(file, args, { stdio: "inherit", windowsHide: true });
  if (result.error) throw result.error;
  if (result.status !== 0)
    throw new Error(`${file} exited with ${result.status}`);
};
mkdirSync(local, { recursive: true });
if (process.argv[2] === "stop") {
  run(pgCtl, ["-D", data, "-m", "fast", "-w", "stop"]);
} else {
  if (!existsSync(join(data, "PG_VERSION"))) {
    const passwordFile = join(local, "initdb-password");
    writeFileSync(passwordFile, "cm-local-only\n", { mode: 0o600 });
    try {
      run(initdb, [
        "-D",
        data,
        "-U",
        "cm",
        "--auth=scram-sha-256",
        `--pwfile=${passwordFile}`,
        "--encoding=UTF8",
        "--locale=C",
      ]);
    } finally {
      unlinkSync(passwordFile);
    }
  }
  const status = spawnSync(pgCtl, ["-D", data, "status"], {
    windowsHide: true,
    stdio: "ignore",
  });
  if (status.status !== 0)
    run(pgCtl, [
      "-D",
      data,
      "-l",
      join(local, "postgres.log"),
      "-o",
      "-h 127.0.0.1 -p 55432",
      "-w",
      "start",
    ]);
  // Provision only this workspace's development database; never drop data.
  const { default: pg } = await import("pg");
  const client = new pg.Client({
    host: "127.0.0.1",
    port: 55432,
    user: "cm",
    password: "cm-local-only",
    database: "postgres",
  });
  await client.connect();
  if (
    !(await client.query("SELECT 1 FROM pg_database WHERE datname = 'cm'"))
      .rowCount
  )
    await client.query("CREATE DATABASE cm");
  await client.end();
  console.log("CM PostgreSQL ready at 127.0.0.1:55432 (database: cm).");
}
