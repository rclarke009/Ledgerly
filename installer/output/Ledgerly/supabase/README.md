# Remote log (Option B): Supabase table + Edge Function

Ledgerly can send sanitized error reports (no PII) to a Supabase Edge Function, which inserts into `remote_log_events`. You view events in the Supabase dashboard.

This path uses **`REMOTE_LOG_URL`** (and related env vars), not **`DATABASE_URL`**. You can keep app data on **local SQLite or local Postgres** and still send logs to a **hosted** Supabase project—see **Hosted Supabase logging** in `setup_and_testing.md`.

## Prerequisites

- Install the [Supabase CLI](https://supabase.com/docs/guides/cli) (e.g. `brew install supabase/tap/supabase` on macOS).
- Log in once: `supabase login`.

## 1. Create the table

In Supabase: **SQL Editor** → New query → paste and run the migration:

- [supabase/migrations/20250311000000_remote_log_events.sql](migrations/20250311000000_remote_log_events.sql)

## 2. Deploy the Edge Function

From the **Ledgerly** project root (the directory that contains this `supabase/` folder):

```bash
cd /path/to/Ledgerly
supabase link --project-ref YOUR_PROJECT_REF
supabase functions deploy ingest-remote-log
```

Use your project ref from the Supabase dashboard URL: `https://app.supabase.com/project/YOUR_PROJECT_REF`. You may be prompted for the database password when linking.

Optional: set a shared secret so only your Ledgerly instances can POST:

```bash
supabase secrets set REMOTE_LOG_SECRET=your-random-secret
```

Set the same value in Ledgerly’s `.env` as `REMOTE_LOG_SECRET`.

## 3. Configure Ledgerly

In Ledgerly’s `.env`:

- `REMOTE_LOG_URL=https://YOUR_PROJECT_REF.supabase.co/functions/v1/ingest-remote-log`
- `REMOTE_LOG_SECRET=` (same as in Supabase secrets, or leave empty to disable auth)
- `REMOTE_LOG_INSTANCE_ID=` (optional; e.g. a UUID to identify “his” instance)

Restart Ledgerly. Errors that hit the exception handlers will be sent to the Edge Function and stored in `remote_log_events`.
