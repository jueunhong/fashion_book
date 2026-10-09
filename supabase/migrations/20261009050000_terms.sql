-- 리뷰에서 추출한 패션 용어 캐시
alter table shows add column if not exists terms jsonb;
alter table shows add column if not exists terms_at timestamptz;
