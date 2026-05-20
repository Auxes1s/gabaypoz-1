-- GabayPoz recommender v2 Supabase migration
-- Purpose:
--   Align live Supabase schema with the v2 scoring contract:
--   - side-by-side v2 questionnaire rows in questions / answer_option
--   - answer_option_scoring_metadata for construct-tagged scoring
--   - program_profile_v2 as the authoritative program-side index
--   - model_recommendation_trace for audit and validation
--   - pilot feedback responses and session-completeness view for evaluation
--
-- Important:
--   This migration must be run by the owner of the affected public tables
--   or a privileged Supabase role.

begin;

alter table public.questions
  add column if not exists model_id text,
  add column if not exists question_code text,
  add column if not exists construct_family text,
  add column if not exists target_field text;

alter table public.answer_option
  add column if not exists question_code text;

alter table public.answer_option
  drop constraint if exists answer_option_question_group_check;

alter table public.answer_option
  add constraint answer_option_question_group_check
  check (question_group in ('internal', 'aptitude', 'constraint', 'aspiration'));

create unique index if not exists questions_model_question_code_uidx
  on public.questions(model_id, question_code)
  where model_id is not null and question_code is not null;

create unique index if not exists answer_option_question_option_label_uidx
  on public.answer_option(question_id, option_label);

create table if not exists public.answer_option_scoring_metadata (
  option_id uuid primary key references public.answer_option(option_id) on delete cascade,
  question_id uuid not null references public.questions(question_id) on delete cascade,
  question_code text not null,
  model_id text not null,
  construct_family text not null,
  target_field text not null,
  response_value double precision,
  reverse_scored boolean not null default false,
  scoring_type text not null
);

create index if not exists answer_option_scoring_metadata_model_question_idx
  on public.answer_option_scoring_metadata(model_id, question_code);

create table if not exists public.program_profile_v2 (
  program_id uuid primary key references public.program(program_id) on delete cascade,
  program_name text not null,
  program_code text,
  profile_version text not null,
  profile_method text not null,
  profile_confidence text not null,
  profile_family text not null,
  dominant_dim text not null,
  dominant_dim_label text not null,
  secondary_dims text,
  evidence_text text not null,
  evidence_sources text not null,
  review_status text not null,
  occupation_bridge_confidence text,
  occupation_bridge_p21_groups text,
  occupation_bridge_p21_labels text,
  affinity_stem_score double precision not null,
  current_stem_score double precision,
  template_stem_score double precision,
  affinity_health_score double precision not null,
  current_health_score double precision,
  template_health_score double precision,
  affinity_arts_score double precision not null,
  current_arts_score double precision,
  template_arts_score double precision,
  affinity_business_score double precision not null,
  current_business_score double precision,
  template_business_score double precision,
  affinity_education_score double precision not null,
  current_education_score double precision,
  template_education_score double precision,
  affinity_agriculture_score double precision not null,
  current_agriculture_score double precision,
  template_agriculture_score double precision,
  affinity_duration_score double precision not null
);

create table if not exists public.model_recommendation_trace (
  trace_id uuid primary key,
  recommendation_id uuid not null references public.model_recommendation(recommendation_id) on delete cascade,
  session_id uuid not null references public.guest_tracker(session_id) on delete cascade,
  model_id text not null,
  rank integer not null,
  program_id uuid not null references public.program(program_id),
  construct_scores jsonb not null,
  constraints jsonb not null,
  warnings jsonb not null default '[]'::jsonb,
  explanation_json jsonb not null,
  created_datetime timestamptz not null
);

create unique index if not exists model_recommendation_trace_recommendation_uidx
  on public.model_recommendation_trace(recommendation_id);

create unique index if not exists model_recommendation_trace_session_model_rank_uidx
  on public.model_recommendation_trace(session_id, model_id, rank);

create table if not exists public.recommender_v2_feedback_response (
  feedback_id uuid primary key,
  session_id uuid not null references public.guest_tracker(session_id) on delete cascade,
  model_id text not null default 'tds_recommender_v2',
  relevance_score integer not null check (relevance_score between 1 and 5),
  surprise_program_text text,
  missing_program_text text,
  acceptance_choice text not null check (acceptance_choice in ('A', 'B', 'C', 'D', 'E')),
  would_consider_any boolean not null,
  non_acceptance_reason text,
  pre_confidence integer not null check (pre_confidence between 1 and 5),
  post_confidence integer not null check (post_confidence between 1 and 5),
  confidence_shift integer generated always as (post_confidence - pre_confidence) stored,
  stated_choice_program text,
  stated_choice_field text check (
    stated_choice_field is null or stated_choice_field in ('stem', 'health', 'arts', 'business', 'education', 'agriculture')
  ),
  followup_consent boolean not null default false,
  created_datetime timestamptz not null default now(),
  updated_datetime timestamptz not null default now()
);

create unique index if not exists recommender_v2_feedback_session_model_uidx
  on public.recommender_v2_feedback_response(session_id, model_id);

create or replace view public.recommender_v2_session_completeness as
select
  gt.session_id,
  'tds_recommender_v2'::text as model_id,
  count(distinct ur.question_id) filter (where q.model_id = 'tds_recommender_v2') as questionnaire_response_count,
  count(distinct mrt.trace_id) as trace_row_count,
  count(distinct fr.feedback_id) as feedback_row_count,
  (
    count(distinct ur.question_id) filter (where q.model_id = 'tds_recommender_v2') >= 29
    and count(distinct mrt.trace_id) >= 3
    and count(distinct fr.feedback_id) >= 1
  ) as session_complete
from public.guest_tracker gt
left join public.users_response ur
  on ur.session_id = gt.session_id
left join public.questions q
  on q.question_id = ur.question_id
left join public.model_recommendation_trace mrt
  on mrt.session_id = gt.session_id
  and mrt.model_id = 'tds_recommender_v2'
left join public.recommender_v2_feedback_response fr
  on fr.session_id = gt.session_id
  and fr.model_id = 'tds_recommender_v2'
group by gt.session_id;

commit;

-- Suggested post-migration loading order:
-- 1. Seed questions from questions_seed_v2.csv
-- 2. Seed answer_option from answer_option_seed_v2.csv
-- 3. Seed answer_option_scoring_metadata from answer_option_scoring_metadata_seed_v2.csv
-- 4. Load program_profile_v2 from data/processed/team4_model/program_profile_v2.csv
--
-- Suggested verification:
-- select count(*) from public.questions where model_id = 'tds_recommender_v2';
-- select count(*) from public.answer_option_scoring_metadata where model_id = 'tds_recommender_v2';
-- select count(*) from public.program_profile_v2;
-- select * from public.recommender_v2_session_completeness where session_complete = true limit 10;
-- select column_name, data_type
-- from information_schema.columns
-- where table_schema = 'public'
--   and table_name in ('questions', 'answer_option', 'answer_option_scoring_metadata', 'program_profile_v2', 'model_recommendation_trace', 'recommender_v2_feedback_response')
-- order by table_name, ordinal_position;
