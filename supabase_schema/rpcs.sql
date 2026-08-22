-- supabase_schema/rpcs.sql
--
-- These are the ORIGINAL maintain_partitions() and refresh_metric_rollups()
-- definitions, as first created against tewartech-project-supabase
-- (dcepcfnnqiwccbnnsdcq) earlier in this project's history. A narrower
-- alternative (metric_rollups-only maintenance; anomalies added to the
-- refresh summary) was briefly applied live on 2026-08-05 and then
-- reverted the same day back to this original version — this file reflects
-- what is actually live now, not the narrower alternative.
--
-- maintain_partitions() covers BOTH metric_rollups and threat_events: it
-- ensures the current + next 2 months' partitions exist for each,
-- complementing drop_old_partitions() (which quota_watchdog() already
-- calls for the trailing edge).
--
-- refresh_metric_rollups() reports current metric_rollups row counts by
-- partition. It does not summarize anomalies — raw samples for metrics
-- live in the D1 edge buffer and R2 archives, not in Postgres, so this is
-- an honest summary of what has already been written here, not a
-- recomputation from source data that isn't present in this database.

create or replace function public.maintain_partitions()
returns jsonb
language plpgsql
set search_path to 'public', 'pg_temp'
as $function$
declare
  v_table text;
  v_month date;
  v_partition_name text;
  v_start timestamptz;
  v_end timestamptz;
  v_created text[] := '{}';
  i integer;
begin
  foreach v_table in array array['metric_rollups', 'threat_events']
  loop
    for i in 0..2 loop
      v_month := (date_trunc('month', now()) + (i || ' months')::interval)::date;
      v_partition_name := v_table || '_' || to_char(v_month, 'YYYYMM');
      v_start := v_month;
      v_end := v_month + interval '1 month';

      if not exists (select 1 from pg_class where relname = v_partition_name) then
        execute format(
          'create table if not exists public.%I partition of public.%I for values from (%L) to (%L)',
          v_partition_name, v_table, v_start, v_end
        );
        v_created := v_created || v_partition_name;
      end if;
    end loop;
  end loop;

  return jsonb_build_object('created_partitions', to_jsonb(v_created), 'checked_at', now());
end;
$function$;

create or replace function public.refresh_metric_rollups()
returns jsonb
language plpgsql
set search_path to 'public', 'pg_temp'
as $function$
declare
  v_total bigint;
  v_by_partition jsonb;
begin
  select count(*) into v_total from public.metric_rollups;

  select coalesce(jsonb_object_agg(relname, cnt), '{}'::jsonb) into v_by_partition
  from (
    select c.relname, count(*) as cnt
    from public.metric_rollups m
    join pg_class c on c.oid = m.tableoid
    group by c.relname
  ) t;

  return jsonb_build_object(
    'total_rows', v_total,
    'by_partition', v_by_partition,
    'refreshed_at', now()
  );
end;
$function$;

-- maintain_threat_event_partitions(): dedicated threat_events partition
-- maintenance, mirroring maintain_partitions()'s logic (current + next 2
-- months, create-if-missing, no ALTER or DROP) but scoped to threat_events
-- only. maintain_partitions() above already covers threat_events too —
-- this function is intentionally redundant with that, not a replacement
-- for it; both are idempotent, so running both is harmless, just double
-- work. Added as its own RPC so a caller can maintain threat_events
-- partitions without also touching metric_rollups.
--
-- Every partition it actually creates is logged as a row in
-- public.security_events (event_type 'threat_event_partition_created') —
-- a partition that already exists produces no log row, since nothing
-- happened. Return type stays `void` (unchanged from the original
-- version) so this remains a plain CREATE OR REPLACE with no signature
-- change; migrations.py additionally only applies this specific function
-- when it does not already exist, so a live deployment's logging is never
-- silently swapped out from under it.
--
-- The insert targets security_events' ACTUAL live column set
-- (id, event_type, severity, detail, created_at) — verified directly
-- against tewartech-project-supabase, which differs from the
-- (event_type, source, details, severity) shape tables.sql documents;
-- see tables.sql's header comment on that pre-existing divergence.
-- `source` has no column of its own here, so it's folded into `detail`.
create or replace function public.maintain_threat_event_partitions()
returns void
language plpgsql
set search_path to 'public', 'pg_temp'
as $function$
declare
  v_month date;
  v_partition_name text;
  v_start timestamptz;
  v_end timestamptz;
  i integer;
begin
  for i in 0..2 loop
    v_month := (date_trunc('month', now()) + (i || ' months')::interval)::date;
    v_partition_name := 'threat_events_' || to_char(v_month, 'YYYYMM');
    v_start := v_month;
    v_end := v_month + interval '1 month';

    if not exists (select 1 from pg_class where relname = v_partition_name) then
      execute format(
        'create table if not exists public.%I partition of public.threat_events for values from (%L) to (%L)',
        v_partition_name, v_start, v_end
      );

      insert into public.security_events (event_type, severity, detail)
      values (
        'threat_event_partition_created',
        'low',
        jsonb_build_object(
          'source', 'maintain_threat_event_partitions',
          'partition_name', v_partition_name,
          'range_start', v_start,
          'range_end', v_end
        )
      );
    end if;
  end loop;
end;
$function$;
