-- 로그인 사용자만 읽기, 즐겨찾기는 사용자별
drop policy if exists "public read shows" on shows;
drop policy if exists "public read seasons" on seasons;
drop policy if exists "public read designers" on designers;
drop policy if exists "public read favorites" on favorites;

create policy "auth read shows" on shows for select to authenticated using (true);
create policy "auth read seasons" on seasons for select to authenticated using (true);
create policy "auth read designers" on designers for select to authenticated using (true);

alter table favorites add column if not exists user_id uuid references auth.users(id) on delete cascade;
create index if not exists favorites_user_idx on favorites (user_id);
create policy "own favorites" on favorites for select to authenticated using (user_id = auth.uid());
