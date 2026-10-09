-- 사용자별 아카이브: 공용 shows 중 내가 담은 것
create table if not exists user_shows (
  user_id uuid not null references auth.users(id) on delete cascade,
  show_key text not null references shows(key) on delete cascade,
  added_at timestamptz not null default now(),
  primary key (user_id, show_key)
);
create index if not exists user_shows_user_idx on user_shows (user_id, added_at desc);
alter table user_shows enable row level security;
create policy "own archive" on user_shows for select to authenticated using (user_id = auth.uid());

-- 기존 쇼는 소유자 계정의 아카이브에 담긴 상태로 시작
insert into user_shows (user_id, show_key)
select '06dd3a67-4d9a-464e-a7fc-618f10fa9466', key from shows
on conflict do nothing;
