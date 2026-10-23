# 아키텍처

글 도우미(PostKit)의 구성 요소, 데이터 흐름, 설계 결정(왜 그렇게 했나), 보안 경계, 시험 전략을 실제 코드 기준으로 정리한다.
첫 소개는 [`../README.md`](../README.md).

## 1. 한눈에

- **대상**: Windows PC 한 대, 사용자 한 명(블로거). 서버·클라우드·회원 가입 없이 그 PC 안에서 끝난다. AI 는 사용자가 이미 로그인해 둔 CLI 를 빌려 쓴다.
- **형태**: `PostKit.exe` 하나(PyInstaller). 실행하면 로컬 HTTP 서버를 띄우고 Edge 를 앱 모드(`--app`, 전용 프로필)로 열어 창처럼 보인다.
- **언어·의존성**: 서버는 **파이썬 표준 라이브러리만**(`http.server`·`socketserver`·`subprocess`·`zipfile`). 사진 손질에만 Pillow. 화면은 외부 CDN 없는 `ui.html` 한 장(바닐라 JS).
- **규모**: 파이썬 약 2,200줄(app 924 · gen 435 · qr 266 · ai 251 · store 215), 화면 1,500줄, 시험 5개 파일 45개.

```
PostKit.exe ── app.main() ── ThreadingHTTPServer 127.0.0.1:8650 ──┬─ GET  /            ui.html (토큰 심어서)
     │                                                           ├─ POST /api/gen      → 플랫폼마다 스레드 → ai.run → <플랫폼>.md
     └─ msedge --app=http://127.0.0.1:8650/                       ├─ GET  /api/job      ← 화면이 2초마다 폴링
                                                                 ├─ POST /api/refine   → ai.run(세션 이어받기) 
                                                                 └─ /api/items · /api/data · /api/backup.zip …
「폰에서 쓰기」 켬 ── PhoneHandler  <LAN IP>:8653 ── PIN → 세션 쿠키 → 같은 라우팅(PC 전용 길은 막음)
```

## 2. 구성 요소

| 구성 요소 | 파일 | 역할 |
|---|---|---|
| 서버 · 창 | `app.py` | 라우팅(`Handler`), 글 만들기 작업(`start_gen`·`gen_one`·`JOBS`), 다듬기(`refine`), 캠페인·장부 저장(`/api/items`), 창 열기·자동 종료, 바로가기, 폰 서버(`PhoneHandler`) |
| 프롬프트 · 결과 | `gen.py` | `build_prompt`(공통 규칙 + 플랫폼 + 말투 + 캠페인 + 아이 규칙 + 사진 목록), 결과 파싱, `ensure_tags`·`apply_campaign`(협찬/공구 표기 문장 `disclosure` 를 `josa` 로 조사 맞춰 앞쪽에 삽입), 사진 손질(`process_photo`), 개월 수 |
| AI 고르기 | `ai.py` | 엔진 목록·설치 확인·사진 보는 법(`photo_mode`: Read 도구 / `--image` 첨부 / base64 / 없음)·엔진별 호출. Ollama 는 `/api/show` capabilities 로 비전 여부를 본다 |
| 저장소 | `store.py` | 데이터 폴더 위치(`location.json`)·옮기기(복사, 원래 자리 남김)·백업 zip/되살리기(되살리기 전 자동 백업)·하루 한 번 자동 백업 7개·성장 기록 모으기 |
| QR | `qr.py` | 바이트 모드·오류 정정 M·버전 1~10 을 직접 구현 — 회사망에서 pip 가 막혀도 되게 |
| 화면 | `ui.html` | 사이드바 탭 7개, 카드·표, AI 티 점검(`lint`)을 화면에서, 서식 복사(`copyRich`), 색 테마 4개(`data-theme`) |
| 프롬프트 파일 | `prompts/*.md` · `platforms.json` · `templates.json` | 코드 수정 없이 플랫폼·메모 틀을 늘린다 |
| 빌드 · 릴리스 | `build.py` · `release.py` · `make_icon.py` | 한 파일 exe · 태그 → GitHub 릴리스 + exe 첨부 |

## 3. 데이터 흐름

### 3.1 글 만들기

1. 화면이 메모·제목을 저장(`/api/post/new` · `/api/post/save`)하고, 사진은 한 장씩 올린다(`/api/photo`). 서버는 받자마자 사진을 손질한다 —
   긴 변 1600, EXIF 회전 반영, GPS 가 있으면 작은 사진도 다시 저장해 위치를 버리고, 찍은 날짜를 돌려줘 화면이 메모 「날짜:」 칸을 채운다.
2. `/api/gen` → `ai.not_ready` 로 엔진을 확인하고, `photo_plan` 으로 사진을 못 보는 모델이면 메모만으로 쓸지·막을지 정한다.
3. 플랫폼마다 스레드 하나(`gen_one`) — `gen.build_prompt` → `ai.run` → `ensure_tags`(늘 붙이는 태그) → `apply_campaign`(표기 문장) →
   `<플랫폼>.md` + `<플랫폼>.history.jsonl`(지시·결과·세션 id·엔진).
4. 화면은 `/api/job?id=` 를 2초마다 불러 끝난 카드부터 채우고, 바로 화면에서 AI 티 점검을 돌린다.

### 3.2 다듬기

`/api/refine` — Claude 로 쓴 글이면 history 의 마지막 `session_id` 로 이어받아 짧은 지시만 보낸다(빠르고 문맥 유지).
다른 엔진이거나 이어받기가 실패하면 규칙·말투·지금 글을 다시 붙인 독립 프롬프트(`standalone=True`)로 새로 부탁한다.
화면은 다듬는 동안 지금 글을 흐리게 남겨 두고 「다듬는 중…」을 띄운다.

### 3.3 캠페인 → 장부

캠페인은 `campaigns.json`, 글 폴더의 `campaign.txt` 가 연결 고리. 조건은 프롬프트에 넣고(AI 가 넣게), 결과는 화면 `lint` 가 다시 센다(키워드 횟수·태그·링크).
협찬·공구 표기 문장은 AI 에게 맡기지 않고 `apply_campaign` 이 직접 넣는다 — 빠지면 법 위반이 될 수 있는 문장이라 결정적이어야 한다.
「완료」 → 장부 입력 칸을 캠페인 값으로 채워 연다. 장부 합계·월별 표·CSV 는 화면에서 계산한다.

### 3.4 앱 수명

창을 닫으면 화면의 `/api/ping`(10초마다)이 끊기고, 45초 지나면 서버가 스스로 끝난다(글을 만드는 중이면 끝난 뒤). 트레이·서비스가 없어 설치·제거가 단순하다.

## 4. 설계 결정

| 결정 | 이유 |
|---|---|
| 자동 발행·로그인 자동화를 만들지 않음 | 네이버 약관 위반·계정 정지 위험. 「글쓰기 창 열기 + 서식 복사」로 붙여 넣기 한 번에 끝나게 만드는 쪽으로 풀었다 |
| API 키 대신 CLI 로그인 | 키를 저장·보호할 필요가 없고, 사용자가 이미 쓰는 구독(Claude·ChatGPT·Gemini)이나 로컬 Ollama 를 그대로 쓴다 |
| AI 티 점검을 AI 없이 화면에서 | 즉시·무료·결정적. 고치는 대로 다시 돌아 「✓ 통과」를 바로 보여 준다. 기준은 `prompts/base.md` 의 금지 표현 목록과 같게 둔다 |
| 표기 문장은 코드가 삽입 | AI 는 빼먹을 수 있다. 받침에 따라 「으로/로」「을/를」 조사도 코드가 붙이고, 앞 4줄에 이미 표기가 있으면 두 번 넣지 않는다 |
| 표준 라이브러리 서버 + HTML 한 장 | 회사망 PC 에서도 pip·CDN 없이 빌드·실행. exe 하나로 배포 |
| 데이터는 평범한 파일(md·json·jsonl) | 사용자가 폴더째 OneDrive 로 옮기거나 zip 으로 백업·이전하기 쉽다. DB 없음 |
| 폰은 같은 화면을 다른 포트로 | 화면 코드를 두 벌로 두지 않는다. 좁은 화면 CSS 와 `PHONE` 플래그(PC 전용 단추 숨김)만 다르다 |
| 색은 CSS 변수(토큰)만 바꾸는 테마 | 화면 코드는 한 벌. WorkKit 허브와 같은 토큰을 복사해 두 앱이 같은 결로 보인다 |

## 5. 보안 경계

| 경계 | 막는 것 | 어떻게 |
|---|---|---|
| 같은 PC 의 다른 웹페이지 | 사용자가 연 악성 페이지가 로컬 API 를 부르는 것(CSRF·DNS 리바인딩) | `127.0.0.1` 바인딩 · `Host` 헤더 검사 · 상태 변경 POST 는 실행마다 새 `X-Token` |
| 같은 와이파이의 다른 기기 | 폰 서버를 엿보거나 PIN 을 맞히는 것 | 켤 때만 열림 · 켤 때마다 새 6자리 PIN · 5번 실패 5분 잠금 · `HttpOnly; SameSite=Strict` 세션 · 세션 값이 곧 POST 토큰 |
| 폰에서 PC 조작 | 폰으로 PC 폴더를 열거나 데이터 위치를 바꾸는 것 | `PHONE_ONLY_PC` 경로 403, `/api/open` 은 폰에선 글쓰기 주소만 돌려줘 폰에서 연다 |
| AI CLI | 프롬프트 주입으로 파일 쓰기·명령 실행 | stdin 프롬프트 · Claude `--allowedTools Read` + `--disallowedTools Bash Write Edit … WebFetch` · Codex `--sandbox read-only` · 작업 폴더 = 그 글 폴더 |
| 사진 · 아이 정보 | 집 위치·아이 신원이 글이나 사진으로 새는 것 | GPS 있으면 다시 저장 · 애칭 규칙을 프롬프트에 · 생일은 개월 수 계산에만 |
| 파일 경로 | `../` 로 데이터 폴더 밖 읽기·지우기 | 이름 정규식 + `gen.inside()` · 본문 크기 제한(JSON 2MB · 파일 30MB) |

## 6. 확장 지점

- **플랫폼 추가**: `platforms.json` 에 한 줄(id·이름·길이·해시태그 수·글쓰기 주소·제목 여부) + `prompts/<id>.md`. 코드 수정 없음.
- **메모 틀 추가**: `templates.json`.
- **AI 엔진 추가**: `ai.py` 의 엔진 표(이름·설치 확인·명령줄·사진 보는 법)에 한 항목과 호출 함수. 시험은 `tests/test_ai.py` 의 가짜 CLI 패턴을 따른다.
- **색 테마 추가**: `ui.html` 의 `:root[data-theme=…]` 토큰 묶음 + `THEMES` 한 줄.

## 7. 시험 전략

- `python -m unittest discover tests` — 45개, 진짜 AI·네트워크를 부르지 않는다.
  - `test_gen` — 프롬프트 조립·결과 파싱·태그·협찬/공구 표기(조사)·개월 수·사진 손질(Pillow 없으면 건너뜀)
  - `test_ai` — 엔진별 명령줄·사진 첨부 방식을 **가짜 CLI 실행 파일**과 **가짜 Ollama HTTP 서버**로 확인
  - `test_store` — 데이터 폴더 옮기기·백업·되살리기·성장 기록 / `test_qr` — QR 인코딩 / `test_release` — 릴리스 스크립트 인자·본문
- CI: GitHub Actions `windows-latest` × 파이썬 3.10·3.12, Pillow 를 깔고 같은 명령.
- 화면은 시험 데이터 폴더(`POSTKIT_DATA`)로 띄워 Playwright(msedge)로 세 테마 × 주요 탭 + 390px 폭을 찍어 콘솔 오류·가로 넘침을 본다(수동 절차).
