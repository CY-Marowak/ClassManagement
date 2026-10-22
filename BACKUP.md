# Encrypted backup and restore

Deployment issue 03. The tools are local implementation; a successful local drill
does not establish that R2 or the daily workflow is operational.

## Prerequisites

Use PostgreSQL client tools matching the source server major version (currently
local PostgreSQL 17), Python 3.12 with `scripts/backup-requirements.txt`, and
[age](https://github.com/FiloSottile/age). Check the Neon server version before
enabling the workflow. Use Neon's direct connection with TLS for backups.

Generate an age identity with `age-keygen -o <private-path>`. Save that identity
outside Git, R2 and GitHub Actions, and keep an independent offline copy. Obtain
its public recipient with `age-keygen -y <private-path>`. The backup runner needs
only the public recipient, never the decryption identity. Losing the identity
means losing the ability to recover its backups. Save the deployed app commit
and `CM_SECRET_KEY` privately as part of recovery preparation as well.

## Export

Set `CM_BACKUP_DATABASE_URL` and `CM_BACKUP_RECIPIENT` through private environment
settings. Do not put connection URLs on command lines, in Git, screenshots or logs.

```text
python scripts/backup.py backup --output <new-path>.dump.age
```

This streams a compressed custom-format `pg_dump` into age; plaintext is not
written to disk. Both processes must succeed. Existing output files are refused;
on failure only the newly created incomplete output is removed. It is a logical
backup of one database, including its tables and migrations, not cluster roles,
external service settings or a point-in-time recovery system.

## R2 and daily workflow

The owner selected guarded R2 operation on 2026-10-22, with avoiding additional
charges as a priority. The account initially showed zero storage and billable
usage; GitHub Actions has an account-wide zero-dollar stop-usage budget.
Keep `CM_BACKUP_ENABLED` unset until setup and restore verification are complete.
The ops CLI limits encrypted files to 50 MiB, projected bucket storage to 1 GiB,
and reserved attempts to one per Taipei day (31 per calendar month), including
failed exports. Incomplete inventory or failed checks stop uploads. These
controls are not an account-wide R2 billing cap. R2 Standard includes 10 GB-month storage,
1 million Class A and 10 million Class B operations monthly; excess usage is
billable and other buckets can consume the same account allowance. Verify
GitHub Actions billing controls too, and keep its zero-dollar stop-usage budget.
[R2 pricing](https://developers.cloudflare.com/r2/pricing/).

The user selected `CY-Marowak/ClassManagement-ops` for the private workflow.
Keep the product repository public; do not put a live backup workflow there.
The ops repository checks out an explicitly reviewed product commit.

Create a dedicated R2 Standard bucket, with r2.dev and custom-domain public access
disabled. Scope the R2 credential to that bucket. Configure an object lifecycle
rule for `cm/daily/` to expire objects after 14 days; do not apply a rule to unrelated
objects. This is a retention period, not a guarantee of exactly 14 files. R2
typically deletes expired objects within 24 hours of expiry, so physical removal
can be later. The tool itself does not perform bulk deletion. See
[R2 lifecycle documentation](https://developers.cloudflare.com/r2/buckets/object-lifecycles/).
Retain `cm/control/` attempt markers for 62 days with a separate lifecycle rule;
never remove them to retry a failed run. Account-wide usage and unrelated manual
requests remain outside the CLI's limits.

The intended schedule is `0 19 * * *` UTC (03:00 Asia/Taipei the following day),
plus manual dispatch. GitHub can delay scheduled runs; it is not an exact-time
service. Keep the workflow on the private repository's default branch. Store
`CM_BACKUP_DATABASE_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` in its Actions
secrets, and `CM_BACKUP_RECIPIENT`, `R2_ACCOUNT_ID`, `R2_BUCKET` in Actions variables.
Do not upload backups as Actions artifacts or commit them to either repository.

Enable Actions email/web notifications for failed workflows for the account
that edits the cron. Test failure notification with the workflow's intentional
failure input, then manually run a real backup and check the object in R2. A red
Actions run alone is not evidence that the owner received a notification. See
[GitHub notification settings](https://docs.github.com/en/subscriptions-and-notifications/how-tos/managing-github-actions-notifications).
Also check the last successful backup timestamp regularly: a workflow that never
starts cannot emit its own failure notification.

## Independent restore

1. Download the chosen `.dump.age` object from the private bucket. Check its
   SHA-256 against the object's `sha256` metadata. Download without public links.
2. Create a dedicated empty database named `cm_restore_<unique-suffix>` on an
   isolated development/restore instance. Never use the production or trial DB.
3. Set `CM_RESTORE_DATABASE_URL` to that target; use the correct TLS options.
4. Run:

```text
python scripts/backup.py restore --input <backup>.dump.age --identity <private-path> --target-db cm_restore_<unique-suffix>
```

The tool verifies the connected database's name and rejects existing user
relations. It fully decrypts/authenticates into one temporary file before executing
SQL. `pg_restore` uses a single transaction, no ownership/ACL restoration and no
`--clean` or database drop. The temporary plaintext file is removed by its exact
path on completion/failure. Use a trusted encrypted local disk for the drill;
interruption or machine failure may leave a temporary file for manual removal.
Use a trusted dump and a dedicated target with no concurrent writers.

5. Start the matching app commit against the restored database with private
   settings, disable real email, then check teacher/student login, classes,
   scores, points, mascot experience and isolation. Compare source snapshot
   evidence captured at backup time, not a production database that kept changing.
6. Record object key, backup time, app revision, tool versions, restore target,
   elapsed time and pass/fail evidence without credentials or personal records.
   Do not switch Render's connection as part of a drill. A real cutover is a
   separate explicit decision, including migration compatibility and write freeze.

## Local integration test

Start the existing local PostgreSQL, put `pg_dump`, `pg_restore`, `age` and
`age-keygen` on PATH, and set `CM_BACKUP_TEST_URL` to its local admin connection.

```text
python scripts/test_backup.py
```

Tests refuse non-local hosts. They create uniquely named databases and keep them
and `.local/backup-test-*` evidence; they do not drop databases or bulk-delete
files. Test identities are disposable test data, never production recovery keys.

References: [pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html),
[pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).
