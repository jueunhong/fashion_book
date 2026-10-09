-- 리뷰 한국어 번역 캐시
alter table shows add column if not exists review_ko text;
alter table shows add column if not exists review_ko_at timestamptz;
