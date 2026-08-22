-- supabase_schema/tables.sql
--
-- APPLIED 2026-08-05 against tewartech-project-supabase (dcepcfnnqiwccbnnsdcq),
-- per explicit approval to run only the missing-table portion of this file.
-- Verified no-op, as expected: test_results, ai_decisions, and
-- security_events already existed there (created by an earlier migration
-- in this same project) with a DIFFERENT column set than what follows here
-- (bigint identity ids, not uuid; different column names) — CREATE TABLE IF
-- NOT EXISTS left all three untouched. This file matches the schema below
-- exactly only against a project where these tables do not yet exist.

create extension if not exists pgcrypto;

create table if not exists public.test_results (
  id uuid primary key default gen_random_uuid(),
  scenario text,
  status text,
  details jsonb,
  metrics jsonb,
  anomalies jsonb,
  created_at timestamptz default now()
);

create table if not exists public.ai_decisions (
  id uuid primary key default gen_random_uuid(),
  decision_type text,
  input jsonb,
  output jsonb,
  confidence numeric,
  created_at timestamptz default now()
);

create table if not exists public.security_events (
  id uuid primary key default gen_random_uuid(),
  event_type text,
  source text,
  details jsonb,
  severity text,
  created_at timestamptz default now()
);

alter table public.test_results enable row level security;
alter table public.ai_decisions enable row level security;
alter table public.security_events enable row level security;
