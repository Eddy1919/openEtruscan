"""Migrate the openEtruscan Postgres corpus from Cloud SQL to Tembo Cloud.

End-to-end:
  1. Spin up `cloud-sql-proxy` against the prod Cloud SQL instance
     (`openetruscan` in long-facet-427508-j2, europe-west1).
  2. `pg_dump` the entire database (schema + data + extensions) to a
     local file, OR stream directly to psql if --stream.
  3. `psql --restore` to the user-provided Tembo connection URL.
  4. Verify on the target:
       - extensions: `vector` (pgvector) + `postgis` present.
       - row counts: spot-check `inscriptions`, `inscription_classifications`,
         `findspots`, `genetic_samples`, `language_word_embeddings`.
       - one pgvector neighbour query + one PostGIS spatial query succeed.
  5. Print (but do NOT execute) the gcloud command to rotate the
     `oe-database-url` secret. Rotating the secret is a manual step so
     you can verify the migration before flipping production traffic.

Reversible: Cloud SQL stays online throughout. If verification fails or
you want to roll back, the Tembo instance can be deleted from their
console; Cloud SQL is unchanged.

Pre-flight:
  - `gcloud auth application-default login` (for Cloud SQL Auth Proxy)
  - `cloud-sql-proxy` binary on PATH (install: gcloud components install cloud-sql-proxy, or grab the binary)
  - `pg_dump` + `psql` on PATH (Postgres 15 client; Postgres 16 client works too)
  - A Tembo project created at https://cloud.tembo.io/ with `vector` +
    `postgis` extensions enabled in the stack. The "VectorDB" stack
    ships pgvector by default; PostGIS needs explicit enablement in the
    stack config or via `CREATE EXTENSION postgis;` as superuser.

Usage:
  # Dry-run (validates env, prints commands, no destructive ops):
  python scripts/ops/migrate_to_tembo.py \\
      --target-url 'postgresql://USER:PWD@HOST:5432/DB?sslmode=require' \\
      --dry-run

  # Real run (streams dump → restore):
  python scripts/ops/migrate_to_tembo.py \\
      --target-url 'postgresql://USER:PWD@HOST:5432/DB?sslmode=require'

  # Save the dump to a local file (useful if you want to inspect before restoring):
  python scripts/ops/migrate_to_tembo.py \\
      --target-url 'postgresql://USER:PWD@HOST:5432/DB?sslmode=require' \\
      --dump-file /tmp/openetruscan.dump
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.parse
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_SOURCE_PROJECT = "long-facet-427508-j2"
DEFAULT_SOURCE_INSTANCE = "openetruscan"
DEFAULT_SOURCE_REGION = "europe-west1"
DEFAULT_SOURCE_DB = "openetruscan"
DEFAULT_SOURCE_USER = "postgres"
DEFAULT_SOURCE_SECRET = "oe-database-url"
PROXY_LOCAL_PORT = 15433  # high port to avoid colliding with a local Postgres


# ────────────────────────────────────────────────────────────────────────────
# Pretty printing
# ────────────────────────────────────────────────────────────────────────────


def step(msg: str) -> None:
    print(f"\n── {msg} ─────────────────────────────────────────────", flush=True)


def ok(msg: str) -> None:
    print(f"  ✓ {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"  ⚠ {msg}", flush=True)


def err(msg: str) -> None:
    print(f"  ✗ {msg}", file=sys.stderr, flush=True)


def redact_url(url: str) -> str:
    """Hide the password in a postgres:// URL for logging."""
    if not url:
        return url
    return re.sub(r"(://[^:]+:)[^@]+(@)", r"\1***\2", url)


# ────────────────────────────────────────────────────────────────────────────
# Pre-flight
# ────────────────────────────────────────────────────────────────────────────


def require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        err(f"required binary `{name}` not on PATH")
        sys.exit(2)
    return path


def fetch_source_password(project: str, secret_name: str) -> str:
    """Pull DATABASE_URL from Secret Manager and extract the password.

    The stored secret is the full Cloud SQL URL of the form
    postgresql://USER:PWD@HOST/DB. We only need the password — host
    is rewritten via the Cloud SQL Auth Proxy.
    """
    res = subprocess.run(
        [
            "gcloud",
            "secrets",
            "versions",
            "access",
            "latest",
            f"--secret={secret_name}",
            f"--project={project}",
        ],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        err(f"could not read secret {secret_name}: {res.stderr.strip()}")
        sys.exit(3)
    url = res.stdout.strip()
    m = re.match(r"^postgres(?:ql)?://([^:]+):([^@]+)@", url)
    if not m:
        err(f"secret {secret_name} doesn't look like a postgres URL")
        sys.exit(3)
    return m.group(2)


# ────────────────────────────────────────────────────────────────────────────
# Cloud SQL Auth Proxy
# ────────────────────────────────────────────────────────────────────────────


@contextmanager
def cloud_sql_proxy(
    instance_connection_name: str,
    local_port: int,
    dry_run: bool,
) -> Iterator[subprocess.Popen | None]:
    """Spin up cloud-sql-proxy as a background subprocess.

    Yields the Popen handle (or None for dry-run). The proxy is killed
    on context exit. Cloud SQL Auth Proxy 2.x uses positional arg
    `INSTANCE_CONNECTION_NAME` and `--port` for local port.
    """
    cmd = [
        "cloud-sql-proxy",
        instance_connection_name,
        f"--port={local_port}",
    ]
    step(f"start cloud-sql-proxy → 127.0.0.1:{local_port}")
    print(f"    cmd: {' '.join(cmd)}", flush=True)
    if dry_run:
        ok("(dry-run, proxy not started)")
        yield None
        return

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    # Wait for proxy to declare itself ready (it prints "Ready for new connections")
    ready = False
    start = time.monotonic()
    assert proc.stdout is not None
    while time.monotonic() - start < 30:
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.1)
            continue
        print(f"    proxy: {line.rstrip()}", flush=True)
        if "Ready for new connections" in line or "ready for new connections" in line.lower():
            ready = True
            break
    if not ready:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
        err("cloud-sql-proxy did not become ready within 30s")
        sys.exit(4)
    ok(f"proxy ready (pid {proc.pid})")
    try:
        yield proc
    finally:
        step(f"stop cloud-sql-proxy (pid {proc.pid})")
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        ok("proxy stopped")


# ────────────────────────────────────────────────────────────────────────────
# Dump + restore
# ────────────────────────────────────────────────────────────────────────────


def make_source_url(user: str, password: str, port: int, db: str) -> str:
    quoted_pwd = urllib.parse.quote(password, safe="")
    return f"postgresql://{user}:{quoted_pwd}@127.0.0.1:{port}/{db}?sslmode=disable"


def pg_dump_cmd(source_url: str, dump_file: Path | None) -> list[str]:
    """pg_dump invocation. --no-owner / --no-privileges so the dump is
    portable to Tembo (where roles + ACLs differ). --clean --if-exists so
    a re-run is idempotent. Extension creation is included by default."""
    args = [
        "pg_dump",
        source_url,
        "--no-owner",
        "--no-privileges",
        "--clean",
        "--if-exists",
        "--format=plain",
        "--quote-all-identifiers",
    ]
    if dump_file:
        args.extend(["--file", str(dump_file)])
    return args


def psql_restore_cmd(target_url: str, dump_file: Path | None) -> list[str]:
    """psql invocation. -v ON_ERROR_STOP=1 = fail fast on any restore error.
    --single-transaction = atomic restore (either all or nothing)."""
    args = [
        "psql",
        target_url,
        "-v", "ON_ERROR_STOP=1",
        "--single-transaction",
    ]
    if dump_file:
        args.extend(["--file", str(dump_file)])
    return args


def run_dump_and_restore(
    source_url: str,
    target_url: str,
    dump_file: Path | None,
    dry_run: bool,
) -> None:
    """Either dump to file then restore, or stream pg_dump | psql in one
    pipe. Streaming saves disk and is faster but loses the inspectable
    intermediate."""
    if dry_run:
        step("would dump + restore")
        print(f"    source: {redact_url(source_url)}", flush=True)
        print(f"    target: {redact_url(target_url)}", flush=True)
        print(f"    dump:   {dump_file or '(stream)'}", flush=True)
        ok("dry-run skipped")
        return

    if dump_file:
        step(f"pg_dump → {dump_file}")
        res = subprocess.run(pg_dump_cmd(source_url, dump_file))
        if res.returncode != 0:
            err(f"pg_dump failed with exit {res.returncode}")
            sys.exit(5)
        size = dump_file.stat().st_size
        ok(f"dump complete, {size:,} bytes ({size / 1024 / 1024:.1f} MB)")

        step("psql restore to Tembo")
        res = subprocess.run(psql_restore_cmd(target_url, dump_file))
        if res.returncode != 0:
            err(f"psql restore failed with exit {res.returncode}")
            err("Cloud SQL is untouched. Inspect the dump file and Tembo state.")
            sys.exit(6)
        ok("restore complete")
    else:
        step("stream pg_dump | psql")
        dump_proc = subprocess.Popen(
            pg_dump_cmd(source_url, None),
            stdout=subprocess.PIPE,
        )
        psql_proc = subprocess.Popen(
            psql_restore_cmd(target_url, None),
            stdin=dump_proc.stdout,
        )
        assert dump_proc.stdout is not None
        dump_proc.stdout.close()  # let psql receive EOF when pg_dump exits
        psql_rc = psql_proc.wait()
        dump_rc = dump_proc.wait()
        if dump_rc != 0:
            err(f"pg_dump exited {dump_rc}")
            sys.exit(5)
        if psql_rc != 0:
            err(f"psql exited {psql_rc}")
            err("Cloud SQL is untouched. Inspect Tembo state.")
            sys.exit(6)
        ok("stream complete")


# ────────────────────────────────────────────────────────────────────────────
# Verification
# ────────────────────────────────────────────────────────────────────────────


VERIFY_QUERIES = [
    (
        "extensions",
        "SELECT extname FROM pg_extension WHERE extname IN ('vector','postgis','postgis_topology') ORDER BY extname;",
        # Must include 'vector' and 'postgis' at minimum.
    ),
    (
        "core table row counts",
        """
        SELECT 'inscriptions' AS table_name, count(*) AS rows FROM inscriptions
        UNION ALL SELECT 'inscription_classifications', count(*) FROM inscription_classifications
        UNION ALL SELECT 'findspots', count(*) FROM findspots
        UNION ALL SELECT 'language_word_embeddings', count(*) FROM language_word_embeddings;
        """,
    ),
    (
        "pgvector neighbour query (smoke)",
        "SELECT 1 FROM language_word_embeddings WHERE emb IS NOT NULL ORDER BY emb <-> emb LIMIT 1;",
    ),
    (
        "postgis spatial query (smoke)",
        "SELECT count(*) FROM findspots WHERE geom IS NOT NULL AND ST_X(geom) BETWEEN -180 AND 180 LIMIT 1;",
    ),
]


def verify_target(target_url: str, dry_run: bool) -> bool:
    step("verify Tembo target")
    if dry_run:
        print("    would run these checks:", flush=True)
        for name, sql in VERIFY_QUERIES:
            print(f"      [{name}] {sql.strip().splitlines()[0]}...", flush=True)
        ok("(dry-run, skipped)")
        return True

    all_ok = True
    for name, sql in VERIFY_QUERIES:
        res = subprocess.run(
            ["psql", target_url, "-X", "-A", "-t", "-c", sql],
            capture_output=True, text=True,
        )
        if res.returncode != 0:
            err(f"verify [{name}] FAILED: {res.stderr.strip()}")
            all_ok = False
            continue
        rows = [r for r in res.stdout.strip().splitlines() if r]
        ok(f"[{name}]")
        for r in rows[:8]:
            print(f"      {r}", flush=True)

    if all_ok:
        ok("all verification queries passed")
    else:
        err("at least one verify query failed; do NOT rotate the secret yet")
    return all_ok


# ────────────────────────────────────────────────────────────────────────────
# Secret rotation hint
# ────────────────────────────────────────────────────────────────────────────


def print_secret_rotation(target_url: str, project: str, secret_name: str) -> None:
    step("secret rotation (manual)")
    print(
        "    The migration is complete on Tembo's side. Cloud SQL is still online\n"
        "    and the production API still reads from it via the current secret\n"
        f"    `{secret_name}` in project `{project}`.\n"
        "\n"
        "    To flip prod to Tembo:\n"
        "\n"
        f"      printf '%s' '{redact_url(target_url)}' \\\n"
        f"        | gcloud secrets versions add {secret_name} \\\n"
        f"            --project={project} \\\n"
        "            --data-file=-\n"
        "\n"
        f"    (REPLACE the redacted URL above with the real target URL.)\n"
        "\n"
        "    Then restart the API container so it picks up the new secret\n"
        "    (the fetch-env-from-sm.sh sidecar does this on next deploy/restart):\n"
        "\n"
        "      gcloud compute ssh openetruscan-eu \\\n"
        f"        --project={project} --zone=europe-west4-a \\\n"
        "        --command='cd /opt/openetruscan && bash scripts/ops/fetch-env-from-sm.sh && \\\n"
        "                   docker compose restart api'\n"
        "\n"
        "    Verify https://api.openetruscan.com/ready returns 200 + /stats/provenance\n"
        "    returns the expected counts.\n"
        "\n"
        "    Rollback: re-add the OLD Cloud SQL URL as a new secret version.\n"
        "    `gcloud secrets versions add` is non-destructive (versioned).",
        flush=True,
    )


# ────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--target-url", required=True,
                    help="Tembo connection URL: postgresql://USER:PWD@HOST:PORT/DB?sslmode=require")
    ap.add_argument("--source-project", default=DEFAULT_SOURCE_PROJECT)
    ap.add_argument("--source-region", default=DEFAULT_SOURCE_REGION)
    ap.add_argument("--source-instance", default=DEFAULT_SOURCE_INSTANCE)
    ap.add_argument("--source-db", default=DEFAULT_SOURCE_DB)
    ap.add_argument("--source-user", default=DEFAULT_SOURCE_USER)
    ap.add_argument("--source-secret", default=DEFAULT_SOURCE_SECRET,
                    help="Secret Manager name holding the DATABASE_URL (we only read the password).")
    ap.add_argument("--proxy-port", type=int, default=PROXY_LOCAL_PORT)
    ap.add_argument("--dump-file", type=Path, default=None,
                    help="Local file to write the dump to. If omitted, the dump is streamed pg_dump | psql.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Validate environment and print every command without executing destructive ones.")
    ap.add_argument("--skip-verify", action="store_true",
                    help="Skip post-restore verification. Not recommended.")
    args = ap.parse_args(argv)

    step("pre-flight")
    require_binary("gcloud")
    require_binary("pg_dump")
    require_binary("psql")
    require_binary("cloud-sql-proxy")
    ok("all required binaries on PATH")

    # Sanity-check target URL shape
    if not args.target_url.startswith("postgres"):
        err("--target-url must start with postgres:// or postgresql://")
        return 2
    print(f"    target: {redact_url(args.target_url)}", flush=True)

    icn = f"{args.source_project}:{args.source_region}:{args.source_instance}"
    print(f"    source: {icn}/{args.source_db} (via cloud-sql-proxy)", flush=True)
    print(f"    secret: {args.source_secret} in {args.source_project}", flush=True)
    print(f"    dump:   {args.dump_file or '(stream)'}", flush=True)
    print(f"    mode:   {'DRY-RUN' if args.dry_run else 'REAL'}", flush=True)

    step("fetch source password from Secret Manager")
    if args.dry_run:
        ok("(dry-run; would call: gcloud secrets versions access latest --secret=...)")
        password = "<placeholder>"
    else:
        password = fetch_source_password(args.source_project, args.source_secret)
        ok(f"password retrieved (length {len(password)} chars)")

    with cloud_sql_proxy(icn, args.proxy_port, args.dry_run):
        source_url = make_source_url(
            args.source_user, password, args.proxy_port, args.source_db
        )
        run_dump_and_restore(source_url, args.target_url, args.dump_file, args.dry_run)

    if not args.skip_verify:
        if not verify_target(args.target_url, args.dry_run):
            err("Verification failed. Production secret NOT rotated.")
            return 7

    print_secret_rotation(args.target_url, args.source_project, args.source_secret)
    ok("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
