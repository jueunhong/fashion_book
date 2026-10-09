-- 사용자별 상태 (최근 본 쇼 등)
create table if not exists user_state (
  user_id uuid primary key references auth.users(id) on delete cascade,
  recent jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now()
);
alter table user_state enable row level security;
create policy "own state" on user_state for select to authenticated using (user_id = auth.uid());
