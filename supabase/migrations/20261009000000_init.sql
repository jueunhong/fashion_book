-- Runway Book 스키마
create table if not exists shows (
  key text primary key,
  season text not null,
  season_name text not null,
  brand text not null,
  brand_name text not null,
  designers text default '',
  event_date text default '',
  pub_date text default '',
  authors jsonb default '[]'::jsonb,
  review_html text default '',
  cover jsonb,
  galleries jsonb not null default '[]'::jsonb,
  looks int not null default 0,
  counts jsonb not null default '{}'::jsonb,
  url text,
  fetched_at timestamptz not null default now()
);
create index if not exists shows_season_idx on shows (season);

create table if not exists seasons (
  slug text primary key,
  name text not null,
  shows jsonb not null default '[]'::jsonb,
  fetched_at timestamptz not null default now()
);

create table if not exists designers (
  slug text primary key,
  name text not null,
  bio_html text default '',
  collections jsonb not null default '[]'::jsonb,
  fetched_at timestamptz not null default now()
);

create table if not exists favorites (
  id text primary key,            -- show_key|gallery_id|n
  show_key text not null,
  gid text not null,
  n int not null,
  item jsonb not null,
  brand text default '',
  season text default '',
  created_at timestamptz not null default now()
);

-- 읽기는 공개(anon), 쓰기는 Edge Function(service role)만
alter table shows enable row level security;
alter table seasons enable row level security;
alter table designers enable row level security;
alter table favorites enable row level security;
create policy "public read shows" on shows for select using (true);
create policy "public read seasons" on seasons for select using (true);
create policy "public read designers" on designers for select using (true);
create policy "public read favorites" on favorites for select using (true);
