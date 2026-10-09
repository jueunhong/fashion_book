-- 관리자 목록
create table if not exists admins (email text primary key);
insert into admins (email) values ('cosmosofficial.manager@gmail.com') on conflict do nothing;

-- AI 사용량 / 이용권
create table if not exists ai_usage (
  user_id uuid primary key references auth.users(id) on delete cascade,
  free_used int not null default 0,          -- 무료 10회 중 사용
  plan text,                                 -- 'month' | 'year'
  plan_until timestamptz,
  plan_quota int not null default 0,
  plan_used int not null default 0,
  updated_at timestamptz not null default now()
);
alter table ai_usage enable row level security;
create policy "own usage" on ai_usage for select to authenticated using (user_id = auth.uid());

-- 이용권 요청
create table if not exists plan_requests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  email text not null,
  status text not null default 'pending',    -- pending | done
  created_at timestamptz not null default now()
);
alter table plan_requests enable row level security;
create policy "own requests" on plan_requests for select to authenticated using (user_id = auth.uid());
