-- 룩 메모 (사용자별)
create table if not exists notes (
  id text primary key,            -- user_id|show_key|gid|n
  user_id uuid not null references auth.users(id) on delete cascade,
  show_key text not null,
  gid text not null,
  n int not null,
  item jsonb not null,
  brand text default '',
  season text default '',
  text text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists notes_user_idx on notes (user_id, updated_at desc);
alter table notes enable row level security;
create policy "own notes" on notes for select to authenticated using (user_id = auth.uid());
