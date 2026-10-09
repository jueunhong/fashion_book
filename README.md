# Runway Book

보그 런웨이(vogue.com/fashion-shows)의 쇼 사진을 가져와 내 컴퓨터에서 편하게 넘겨 보는 개인용 뷰어.
파이썬 3 표준 라이브러리만 사용하며 별도 설치가 필요 없습니다.

## 실행

```bash
cd ~/Desktop/fashion_book
python3 server.py          # 브라우저가 http://localhost:8765 로 자동 열림
```

종료는 터미널에서 `Ctrl+C`.

## 사용법 (웹 UI)

- **URL로 가져오기**: 상단 입력창에 보그 쇼 URL을 붙여넣고 `가져오기`.
  예) `https://www.vogue.com/fashion-shows/spring-2026-ready-to-wear/chanel`
  시즌 URL이나 디자이너 URL을 넣으면 해당 목록 화면으로 이동합니다.
- **시즌**: 시즌을 고르고 `목록 불러오기` → 쇼별 `가져오기` 또는 `전체 가져오기`.
- **브랜드**: 브랜드 슬러그(예: `chanel`, `louis-vuitton`)로 전체 아카이브 목록을 보고 `최근 N개 가져오기`.
- **쇼 보기**: Collection / Details 탭, 크기 슬라이더, 클릭하면 크게 보기(← → 이동, F 즐겨찾기, Esc 닫기).
  주소창의 `#/show/<쇼>/<갤러리>/<룩번호>` 가 현재 보고 있는 룩을 가리키므로 북마크해 두면 그 룩으로 바로 열립니다.
- **이미지 저장(오프라인)**: 쇼 화면의 버튼을 누르면 `data/images/` 에 1600px 이미지를 받아 둡니다. 이후에는 인터넷 없이도 볼 수 있습니다.
- **즐겨찾기**: 브라우저 localStorage 에 저장됩니다(브라우저를 바꾸면 사라짐). `JSON 내보내기`로 백업할 수 있습니다.

## 사용법 (터미널)

```bash
python3 vogue.py show spring-2026-ready-to-wear/chanel            # 쇼 하나
python3 vogue.py show <URL> --download                           # 이미지까지 저장
python3 vogue.py season spring-2026-ready-to-wear --all          # 시즌 전체 (300여 개, 쇼당 약 1초)
python3 vogue.py designer chanel --all --limit 20                # 브랜드 최근 20시즌
python3 vogue.py index                                           # data/index.json 재생성
```

## 로그인(구독) 쿠키

현재 보그 런웨이 페이지는 로그인 없이도 전체 룩 목록을 담고 있어 쿠키 없이 동작합니다.
나중에 특정 페이지가 "contentRestricted" 로 막히면, 브라우저 확장(예: *Get cookies.txt LOCALLY*)으로
vogue.com 쿠키를 **Netscape 형식** `cookies.txt` 로 내보내 이 폴더에 두면 자동으로 사용합니다.
(`--cookies 경로` 옵션으로 위치를 지정할 수도 있습니다.)

## 배포 (Vercel + Supabase)

배포 주소: https://runway-book.vercel.app (Vercel 프로젝트 runway-book)

Vercel 이 빌드 단계에서 `python3 export.py` 를 실행하므로(`vercel.json`), 로컬에서 export 를 돌리지 않아도 됩니다.
Supabase 주소와 anon 키는 Vercel 프로젝트 환경 변수(`SUPABASE_URL`, `SUPABASE_ANON_KEY`)에 들어 있습니다.
GitHub 저장소를 연결하면 `git push` 만으로 자동 배포됩니다.

배포본은 **Supabase** 를 저장소와 수집 서버로 씁니다. 폰에서도 시즌 목록 불러오기와 가져오기가 되고,
어느 기기에서 가져오든 같은 보관함에 쌓이며, 즐겨찾기도 기기 간에 동기화됩니다.

- **이메일 + 비밀번호 로그인**이 필요합니다. 보기, 가져오기, 삭제, 즐겨찾기 모두 로그인한 사용자만 가능합니다.
  계정은 `.env.local` 의 `LOGIN_EMAIL` / `LOGIN_PASSWORD` 이며, 로그인 후 상단 `비밀번호 변경` 으로 바꿀 수 있습니다.
- 로그인 화면의 `회원가입` 으로 누구나 계정을 만들 수 있습니다(이메일 확인 없이 바로 가입, 비밀번호 8자 이상).
  가입한 사람은 보관함 전체를 보고 가져오기도 할 수 있으며, 즐겨찾기만 각자 따로 저장됩니다.
- 가입을 다시 막으려면 `supabase/config.toml` 의 `enable_signup = false` 로 바꾸고 `npx supabase config push` 를 실행합니다.
  Edge Function 시크릿 `ALLOWED_EMAILS` (쉼표 구분)를 설정하면 그 이메일만 가져오기·삭제·즐겨찾기 저장을 할 수 있습니다.
- 시즌 전체 가져오기는 브라우저가 쇼를 하나씩 차례로 요청합니다(쇼당 약 2초). 끝날 때까지 탭을 열어 두세요.
- 이미지 오프라인 저장은 배포본에서 지원하지 않습니다. 사진은 보그 CDN 에서 바로 불러옵니다.

구성 파일:

```
supabase/functions/vogue/index.ts     수집 Edge Function (vogue.py 의 TypeScript 이식)
supabase/migrations/*.sql             shows / seasons / designers / favorites 테이블
sync_to_supabase.py                   로컬 data/ → Supabase 올리기 (--pull 은 반대 방향)
export.py                             뷰어를 dist/ 로 내보내며 .env.local 의 Supabase 설정을 주입
.env.local                            비밀 정보(키, 비밀번호). git 에 올리지 말 것
```

다시 배포할 때:

```bash
npx supabase functions deploy vogue --no-verify-jwt   # 함수를 고쳤을 때
npx supabase db push                                  # 마이그레이션을 추가했을 때
git push                                              # 뷰어를 고쳤을 때 (GitHub 연결 후 자동 배포)
npx vercel --prod --yes                               # 또는 CLI 로 직접 배포
```

- 처음 한 번은 `npx vercel login`, `npx supabase login` 이 필요합니다.
- Supabase 무료 프로젝트는 일주일간 접속이 없으면 일시정지되며, 대시보드에서 다시 켜면 됩니다.
- 보그 사진이 공개 주소에 올라가므로 주소를 함부로 공유하지 마세요.

## 데이터 구조

```
data/
  index.json                 가져온 쇼 목록(보관함)
  shows/<season>__<brand>.json   쇼 메타데이터 + 갤러리별 사진 ID 목록 + 리뷰 본문
  seasons/<season>.json      시즌의 쇼 목록
  designers/<brand>.json     브랜드의 시즌 목록
  images/<show>/<gallery>/NNN.jpg   오프라인 저장 이미지(선택)
```

사진은 기본적으로 `assets.vogue.com` 에서 바로 불러오며, 원하는 크기(`w_640`, `w_2000`, 원본 `pass`)로 요청합니다.

## 주의

- 사진의 저작권은 보그 및 각 촬영자에게 있습니다. 개인 열람용으로만 사용하세요.
- 보그 서버에 부담을 주지 않도록 요청 간 0.8초 간격을 둡니다. 한 시즌 전체(약 350개 쇼)는 6~7분 정도 걸립니다.
- 보그가 페이지 구조를 바꾸면 수집이 실패할 수 있습니다. 그 경우 `vogue.py` 의 `fetch_show` 를 수정해야 합니다.
