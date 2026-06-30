-- Remote log events: sanitized error/warning reports from Ledgerly instances (no PII).
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor → New query).

create table if not exists public.remote_log_events (
  id uuid primary key default gen_random_uuid(),
  received_at timestamptz not null default now(),
  timestamp text not null,
  level text not null check (level in ('ERROR', 'WARNING', 'INFO')),
  route text,
  request_id text,
  trace_id text,
  duration_ms integer,
  error_type text,
  message text not null,
  stack_trace text,
  instance_id text
);

comment on table public.remote_log_events is 'Remote log events from Ledgerly instances; no PII.';
create index if not exists idx_remote_log_events_received_at on public.remote_log_events (received_at desc);
create index if not exists idx_remote_log_events_level on public.remote_log_events (level);
create index if not exists idx_remote_log_events_instance_id on public.remote_log_events (instance_id);

-- Optional: restrict inserts to service role (Edge Function uses service role).
-- RLS: allow insert from service role only; no public/anon access.
alter table public.remote_log_events enable row level security;

create policy "Service role can insert remote_log_events"
  on public.remote_log_events for insert
  to service_role
  with check (true);

create policy "Service role can select remote_log_events"
  on public.remote_log_events for select
  to service_role
  using (true);
