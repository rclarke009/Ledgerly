// Supabase Edge Function: accept POST with sanitized log payload, validate, insert into remote_log_events.
// Deploy: supabase functions deploy ingest-remote-log
// Optional: set REMOTE_LOG_SECRET in Supabase secrets; Ledgerly sends it as X-Remote-Log-Secret.

import { createClient } from "npm:@supabase/supabase-js@2";

const ALLOWED_LEVELS = ["ERROR", "WARNING", "INFO"] as const;
const MAX_MESSAGE_LENGTH = 2000;
const MAX_STACK_TRACE_LENGTH = 5000;

interface RemoteLogPayload {
  timestamp: string;
  level: string;
  route?: string | null;
  request_id?: string | null;
  trace_id?: string | null;
  duration_ms?: number | null;
  error_type?: string | null;
  message: string;
  stack_trace?: string | null;
  instance_id?: string | null;
}

function validatePayload(body: unknown): { ok: true; payload: RemoteLogPayload } | { ok: false; status: number; error: string } {
  if (body == null || typeof body !== "object" || !("timestamp" in body) || !("level" in body) || !("message" in body)) {
    return { ok: false, status: 400, error: "Missing required fields: timestamp, level, message" };
  }
  const ts = (body as Record<string, unknown>).timestamp;
  const level = (body as Record<string, unknown>).level;
  const message = (body as Record<string, unknown>).message;
  if (typeof ts !== "string" || typeof level !== "string" || typeof message !== "string") {
    return { ok: false, status: 400, error: "timestamp, level, message must be strings" };
  }
  if (!ALLOWED_LEVELS.includes(level as (typeof ALLOWED_LEVELS)[number])) {
    return { ok: false, status: 400, error: "level must be one of ERROR, WARNING, INFO" };
  }
  if (message.length > MAX_MESSAGE_LENGTH) {
    return { ok: false, status: 400, error: "message too long" };
  }
  const payload: RemoteLogPayload = {
    timestamp: ts,
    level,
    message: message.slice(0, MAX_MESSAGE_LENGTH),
    route: optionalString(body, "route"),
    request_id: optionalString(body, "request_id"),
    trace_id: optionalString(body, "trace_id"),
    duration_ms: optionalInt(body, "duration_ms"),
    error_type: optionalString(body, "error_type"),
    stack_trace: truncate(optionalString(body, "stack_trace"), MAX_STACK_TRACE_LENGTH),
    instance_id: optionalString(body, "instance_id"),
  };
  return { ok: true, payload };
}

function optionalString(obj: Record<string, unknown>, key: string): string | null {
  const v = obj[key];
  if (v == null) return null;
  if (typeof v !== "string") return null;
  return v;
}

function optionalInt(obj: Record<string, unknown>, key: string): number | null {
  const v = obj[key];
  if (v == null) return null;
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const n = parseInt(v, 10);
    if (Number.isFinite(n)) return n;
  }
  return null;
}

function truncate(s: string | null, max: number): string | null {
  if (s == null) return null;
  if (s.length <= max) return s;
  return s.slice(0, max) + "...";
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type, X-Remote-Log-Secret" } });
  }
  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "Method not allowed" }), { status: 405, headers: { "Content-Type": "application/json" } });
  }

  const secret = Deno.env.get("REMOTE_LOG_SECRET");
  if (secret) {
    const provided = req.headers.get("X-Remote-Log-Secret");
    if (provided !== secret) {
      return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401, headers: { "Content-Type": "application/json" } });
    }
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return new Response(JSON.stringify({ error: "Invalid JSON" }), { status: 400, headers: { "Content-Type": "application/json" } });
  }

  const validated = validatePayload(body);
  if (!validated.ok) {
    return new Response(JSON.stringify({ error: validated.error }), { status: validated.status, headers: { "Content-Type": "application/json" } });
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!supabaseUrl || !serviceRoleKey) {
    return new Response(JSON.stringify({ error: "Server configuration error" }), { status: 500, headers: { "Content-Type": "application/json" } });
  }

  const supabase = createClient(supabaseUrl, serviceRoleKey);
  const { error } = await supabase.from("remote_log_events").insert({
    timestamp: validated.payload.timestamp,
    level: validated.payload.level,
    route: validated.payload.route ?? null,
    request_id: validated.payload.request_id ?? null,
    trace_id: validated.payload.trace_id ?? null,
    duration_ms: validated.payload.duration_ms ?? null,
    error_type: validated.payload.error_type ?? null,
    message: validated.payload.message,
    stack_trace: validated.payload.stack_trace ?? null,
    instance_id: validated.payload.instance_id ?? null,
  });

  if (error) {
    return new Response(JSON.stringify({ error: error.message }), { status: 500, headers: { "Content-Type": "application/json" } });
  }
  return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" } });
});
