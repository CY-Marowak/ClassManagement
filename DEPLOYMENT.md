# CM deployment and operations

Phase 1: Render Free + Neon Free. Email delivery and independent backups are
separate follow-up tasks; do not invite a real class until those are verified.

## Build and start

The root Dockerfile builds React with Node 22, then runs Django on Python 3.12.
WhiteNoise serves `frontend/dist` on the same origin as `/api/`. The app uses
hash routes, so refreshing `/#student-login` or an action link requests `/`.
Missing API routes and assets return 404 rather than the app HTML.

`render.yaml` declares one Free Docker web service in Singapore, with automatic
deploys disabled. It does not create a Render database. The health endpoint
`/healthz` checks only the process and does not access Neon or create sessions.

Startup runs `check --deploy --fail-level WARNING`, applies migrations, and
starts one Gunicorn worker with four threads. Only backwards-compatible
migrations can use this startup sequence while an old deployment still serves
traffic. There are no new migrations in this deployment change.

## Private settings

- `DATABASE_URL`: Neon PostgreSQL connection string with SSL. Use the pooled
  endpoint for the web app. Django closes connections after each request and
  disables server-side cursors for transaction pooling.
- `CM_SECRET_KEY`: generated random value, stable across deployments.
- `CM_DEBUG=0`.
- `CM_TRUST_RENDER_PROXY=1`: only behind Render's TLS-terminating proxy. Render
  controls the forwarded HTTPS header; do not enable this for a directly exposed
  server or an untrusted proxy.
- `CM_ALLOWED_HOSTS` and `CM_FRONTEND_URL` default to Render's external hostname.
  Set both explicitly if using a different hostname. The origin must use HTTPS.

Do not copy local development database credentials to Render. `.env.example`
is documentation only; Django does not automatically load `.env` files.
Keep credentials in platform secrets or ignored local files. Access logs omit
query strings, headers, cookies and bodies; action tokens use URL fragments.

## First fake-data deployment

1. Confirm the target Neon database is dedicated to CM and empty before its first
   migration. Do not run the automated suite against this database.
2. Publish the reviewed app commit to its own GitHub repository, then create the
   service from the Blueprint or the equivalent Docker configuration.
3. Confirm `/healthz`, `/`, hashed JavaScript/CSS, and `/api/csrf/` over HTTPS.
4. Seed fake accounts explicitly from a trusted local terminal with the same
   secret settings, `CM_DEBUG=0` and `CM_ALLOW_DEMO_DATA=1`, using
   `python backend/manage.py create_demo`. Save its output privately; it contains
   passwords. Never run this automatically on deploy or put its output in Render
   logs. Reset the local flag after the command. It creates new independent data
   and never resets or deletes existing data.
5. Walk through teacher login, creating a class, importing fake students, scoring,
   awarding points, student first-password change, and feeding. Also verify an
   unrelated class/account cannot access the data. Record the deployed commit.
6. Restart/redeploy and check the same account and data still work. Record cold
   start delay. A Free service sleeps when idle; no keep-alive job is included.

The default email transport is not configured for this phase. Use the seeded
verified teacher accounts; email registration/recovery is not accepted until
the Resend task is complete. Do not enable DEBUG to work around missing email.

## Before a real trial

- Configure Resend HTTPS email delivery with a verified sending domain, and test
  receipt, expiry, single use and recovery links on the public origin.
- Configure daily encrypted PostgreSQL dumps to a private R2 Standard bucket,
  failure notifications, retention, and an independent-database restore drill.
- Use a separate empty database for real trial data; the demonstration database
  remains fake-only. Never share real student accounts in a public demo.
- Verify proxy client-IP handling for authentication rate limits. Currently
  `REMOTE_ADDR` is used conservatively; on Render different clients may share a
  proxy's bucket. Do not trust arbitrary forwarded IP headers to fix this. Test
  expected class login load before the trial and document the proxy trust chain.
- Check free quota consumption for all services in the Render workspace, Neon
  compute/transfer usage, R2 storage/operations, and Actions minutes. Do not add a
  probe that repeatedly queries Neon just to keep it awake.

## Updates and recovery

Before each release, review migration compatibility and take an independent
backup once the backup workflow is available. Deploy an explicit reviewed commit.
Check health and one authenticated core workflow after release. A failed build
does not prove the previous deployment stopped serving; check service status.

Code rollback is separate from database recovery. Revert to a compatible commit;
do not blindly reverse migrations. Restore backups to an independent database,
verify them, and then deliberately switch the connection setting. Never test a
restore by overwriting the active database.

The health response is not a database or email availability guarantee. Inspect
service logs for failures and verify the affected workflow directly.
