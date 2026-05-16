-- GabayPoz recommender v1.2 model_recommendation migration
-- Purpose:
--   Align public.model_recommendation with recommender_v1_2.py persisted rows:
--   session_id, model_id, rank, program_id, university_id, model_score,
--   created_datetime.
--
-- Important:
--   This migration must be run by the owner of public.model_recommendation
--   or a privileged Supabase role. The Team 4 read/write DB URL can insert
--   data but cannot ALTER this table.

begin;

alter table public.model_recommendation
  add column if not exists model_id text,
  add column if not exists rank integer,
  add column if not exists university_id uuid;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'model_recommendation_university_id_fkey'
      and conrelid = 'public.model_recommendation'::regclass
  ) then
    alter table public.model_recommendation
      add constraint model_recommendation_university_id_fkey
      foreign key (university_id)
      references public.university(university_id);
  end if;
end $$;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'model_recommendation_rank_check'
      and conrelid = 'public.model_recommendation'::regclass
  ) then
    alter table public.model_recommendation
      add constraint model_recommendation_rank_check
      check (rank in (1, 2, 3));
  end if;
end $$;

create unique index if not exists model_recommendation_session_model_rank_uidx
  on public.model_recommendation(session_id, model_id, rank);

-- Safe today because live model_recommendation had 0 rows when checked.
-- If rows exist before this migration is run, backfill them before enabling
-- NOT NULL.
alter table public.model_recommendation
  alter column model_id set not null,
  alter column rank set not null,
  alter column university_id set not null;

commit;

-- Verification:
-- select column_name, data_type, is_nullable
-- from information_schema.columns
-- where table_schema = 'public'
--   and table_name = 'model_recommendation'
-- order by ordinal_position;
--
-- select conname, contype
-- from pg_constraint
-- where conrelid = 'public.model_recommendation'::regclass
-- order by conname;

-- Rollback, after exporting any rows that need to be preserved:
--
-- begin;
-- drop index if exists public.model_recommendation_session_model_rank_uidx;
-- alter table public.model_recommendation
--   drop constraint if exists model_recommendation_rank_check,
--   drop constraint if exists model_recommendation_university_id_fkey,
--   drop column if exists model_id,
--   drop column if exists rank,
--   drop column if exists university_id;
-- commit;
