# swbins-kit2 — 둥이로그 (쌍둥이 엄마·아빠의 글쓰기 응용프로그램)

사진·메모를 넣으면 블로그·카페·인스타·틱톡용 글을 **내 말투로** 써 주고 다듬어 주는 응용프로그램 — 윈도우 `DungiLog.exe` 하나, 맥 `DungiLog.app`(2026-10-23 맥 지원 추가, 아래 「맥 지원」).
**이름**: 2026-10-26 「글 도우미(PostKit)」→ **둥이로그(DungiLog)** — 원래 쌍둥이 엄마·아빠가 쓰려고 만든 것. 바꾼 건 화면 이름·exe·앱 이름·릴리스 파일·바로가기(옛 「글 도우미.lnk」는 바로가기 만들 때 치움)뿐이고, **데이터 폴더(`%APPDATA%\PostKit` 등)·`POSTKIT_DATA`·백업 표시 `postkit-backup.json`·맥 번들 ID·달력 UID(`@postkit`)는 기존 데이터·권한·일정이 이어지게 일부러 그대로** 둔다 — 바꾸지 말 것.
**올리는 건 사람이 한다** — 자동 발행·자동 로그인·브라우저 조작은 이 저장소에 넣지 않는다(네이버 약관·계정 정지 위험, 2026-10-19 사용자 결정).

> 이 파일이 **정본**이다. 다른 PC 의 Claude Code 도 이 파일만 읽으면 이어서 할 수 있게 적는다 — 상태가 바뀌면 여기 「지금 상태」를 고친다.
> `DESIGN.md` 는 첫 판 설계서(2026-10-19)라 그 뒤 기능은 없다. 역사 참고용.

## 지금 상태 (2026-10-26, 릴리스 v0.4.4 — 세금용 엑셀 · 썸네일·카드뉴스 · 올린 뒤 검수 · 일정·달력 · 사진 개수 · 참고 글)

다 된 것 — 화면 탭 순서대로(아래 이모지는 옛 탭 이름 — 지금 화면은 선 아이콘):
- **✍️ 쓰기**: 메모·사진(끌어 놓기·붙여넣기·끌어서 순서 바꾸기) → 플랫폼 고르기 → 플랫폼별 카드(병렬 `claude -p`), 말로/버튼으로 다듬기(세션 이어받기), 복사(블로그·카페는 제목 / 본문 서식 따로) — 본문 복사와 글쓰기 창 열기는 단추 하나, 「새로 고른 곳만 만들기」, 참고할 글 주소(비슷한 블로그·인스타 3개까지, `refs.py` 가 읽어 구성만 참고 — 문장·사실은 옮기지 않게 프롬프트로 막음), AI 티 점검(화면에서, 뻔한 표현·같은 끝맺음·고른 문단·이모지 반복·캠페인 조건), 「🗣 내 말투로 저장」, 🖼 썸네일·카드뉴스(사진이 있으면 글 카드 아래 — 블로그 썸네일 1:1·인스타 카드 4:5, 모양 3가지(아래 띠·가운데·흰 테두리), 한 줄에 한 장·`[사진 n]` 으로 배경 고르기, 블로그 소제목으로 채우기. 화면 캔버스로 그려 이 PC 한글 글꼴 그대로, 저장은 글 폴더 `cards` (`/api/card`)).
  메모 틀 `templates.json`(맛집·카페·제품 후기·여행·👶 쌍둥이 육아·일상) — 빈 칸은 글에 안 넣는다(prompts\base.md 규칙).
  사진은 넣을 때 긴 변 1600·EXIF 회전·GPS 있으면 다시 저장(위치 지움), 찍은 날짜를 메모 「날짜:」 칸에, 아기 생일이 있으면 「개월 수:」 칸에.
- **🗣️ 내 말투**: 내가 쓴 글(voice\*.txt, 최근 5편·1500자) + 말투 메모.
- **📂 지난 글**: 다시 열기 · **👶 성장 기록**(「개월 수」 있는 글을 개월 순, 골라서 모은 메모+대표 사진으로 새 글).
- **🎁 캠페인**: 체험단·협찬·공구 — 필수 키워드(횟수)·태그·링크·요구사항을 프롬프트에, 협찬/공구 표기 문장은 앱이 직접 넣음(`gen.apply_campaign`, 받침 따라 조사), 마감 3일 전 배지, 「완료」→ 장부, 「검수」(올린 글 주소 → `audit.py` 가 키워드·태그·링크·사진 수·지도·협찬 표기 위치 확인, 업체 보고 글 복사. 네이버는 se-image-resource·se-placesMap·gsTagName 으로 셈 — 에디터가 바뀌면 여기부터 본다), 📅 다가오는 일정(방문·체험 예약 날짜·시간·마감·공구 시작, 앱 열 때 오늘·내일 안내) + 「달력에 넣기」 `.ics`(`cal.py`, 전날·당일 알림 — 앱이 꺼져도 폰·PC 달력이 알림).
- **📒 장부**: 받은 돈·물품 가액·떼인 세금(원천징수, 「3.3%」 단추 = 3% + 0.3% 각각 10원 미만 버림)·글 주소, 연도 합계·월별 표, 「세금용 엑셀」(`taxbook.py` → 요약·내역·월별·업체별 4장, 수식+미리 계산한 값. xlsx 는 의존성 없이 `xlsx.py` 가 zipfile 로 씀 — 2026-10 이 PC 엑셀로 열어 확인). 세금 계산·소득 구분은 하지 않는다(홈택스·세무사 몫).
- **⚙️ 설정**: 🤖 AI 고르기(Claude Code 기본 · Codex · Gemini CLI · Ollama — `ai.py`, 2026-10-23) · 💾 데이터 폴더 옮기기(OneDrive·구글 드라이브·폴더 고르기, 복사·원래 자리 남김, 이미 데이터 있으면 그대로 씀) · 백업 zip 받기/되살리기 · 하루 한 번 자동 백업 · 📱 폰에서 쓰기 · 👶 아기 생일·애칭(글엔 애칭만) · 늘 붙이는 해시태그 · 카페 글쓰기 주소 · 바로가기 다시 만들기.
- **📱 폰에서 쓰기**: 켤 때만 LAN 주소:8653(PhoneHandler), QR(`qr.py` 자체 구현)·6자리 PIN → HttpOnly 세션, 5번 틀리면 5분 잠금, PC 를 건드리는 길 막음, 좁은 화면은 탭이 아래로.
- **❓ 도움말** 탭, 첫 실행 때 도움말 먼저, exe 처음 실행 때 바탕 화면·시작 메뉴 바로가기.

**아직 실제로 확인 못 한 것**(사용자가 써 보고 알려 주기로 함 — 다음 세션은 사용 후기부터):
1. 네이버 블로그 에디터에 「본문 복사 + 글쓰기 창」 붙여 넣었을 때 모양(소제목 크기·줄 간격)
2. 진짜 아이폰으로 폰에서 쓰기(집 와이파이) — 시험 브라우저로만 확인
3. 말투가 얼마나 비슷한지, AI 티 점검 기준이 적당한지

**맥 지원**(2026-10-23, 이 PC 는 윈도우라 맥 빌드·시험은 GitHub Actions `macos-latest` 로만 했다):
- OS 가 갈리는 곳은 `docs/ARCHITECTURE.md` 8절 표가 정본 — 데이터 `~/Library/Application Support/PostKit`(로컬 `…/PostKit-local`, 로그 `~/Library/Logs/PostKit`),
  앱 창 Chrome·Edge·Brave `--app`(없으면 기본 브라우저), 폴더 고르기 `osascript`, 바로가기 없음, 클라우드 `~/Library/CloudStorage`·iCloud,
  CLI 찾기는 로그인 셸 PATH + 흔한 설치 폴더(`gen.search_path`), 한글 파일 이름 NFC.
- 빌드는 맥에서 `python build.py` → `dist/DungiLog.app` + `dist/DungiLog-mac.zip`(서명·공증 없음, arm64). CI 의 `build` 작업이 만들어 `DungiLog-mac` 아티팩트로 14일 올려 둔다. 릴리스엔 아직 안 올림.
- **진짜 맥에서 아직 확인 못 한 것**: 처음 열기(Gatekeeper)·Chrome 앱 창이 뜨는지·폴더 고르기 창·Finder 로 켰을 때 claude 찾기·사진 끌어 놓기/⌘V·서식 복사·폰에서 쓰기 방화벽 묻기·창 닫은 뒤 다시 켜기.

**사용자 결정·취향**(다시 묻지 말 것):
- 쓰는 사람은 일단 나만 → AI 는 각 CLI 로그인(기본 Claude Code, 2026-10-23 부터 Codex·Gemini CLI·로컬 Ollama 도 고를 수 있음). API 키 방식은 쓰지 않는다(판매판 때 다시).
- 부업 방향: **체험단·협찬·공구** + **쌍둥이 아기 육아 일상** 글. 카카오 쪽은 "잘 모르겠으니 패스".
- 「AI 글 티」는 속이는 기능이 아니라 내 말투·사실 재료·뻔한 표현 걷어내기로 푼다. 광고·AI 표시를 숨기는 기능은 안 만든다.
- 기능 추천은 멈춘 상태 — **써 본 뒤 나온 요청만** 넣는다. 넣기 전에 "굳이 필요?" 부터 따진다. 속도 중시.

## 파일

```
app.py            서버·창·라우팅·폰 서버(PhoneHandler)·데이터 폴더/백업 길
gen.py            프롬프트 조립·claude -p 호출·결과 파싱·사진 손질·태그/협찬 표기·아기 개월 수 (테스트 대상)
ai.py             AI 고르기 — 엔진 목록·설치 확인·엔진별 호출(codex exec·gemini -p·Ollama /api/chat)·사진 보는 법 (테스트 대상)
store.py          데이터 폴더 위치(location.json)·복사·백업 zip/되살리기·자동 백업·성장 기록 (테스트 대상)
qr.py             QR(바이트·M·버전 1~10) — 외부 라이브러리 없이
ui.html           화면 전부(바닐라 JS, 외부 CDN 없음). 색은 키트(C:\swbins-kit) 허브 web\theme.css 토큰을 :root 변수로 복사해 씀
                  — <html data-theme> basic(기본, 흰+파랑)·navy(진한 사이드바)·dark·pastel(예전 모양), 고른 값은 localStorage "theme"(창마다)
                  아이콘은 IC 표의 선(stroke) SVG(<svg class="i" data-i="이름"> / JS 에선 ic("이름")) — 탭·단추에 이모지를 다시 넣지 말 것
docs\             ARCHITECTURE.md(설계 설명) · images\ui-<탭>-<테마>.png(README 스크린샷 — 견본 데이터는 가상, 경로·이름 같은 개인 정보 없게)
.github\workflows\test.yml   unittest: windows·macos × 파이썬 3.10·3.12 / build: 두 OS 에서 build.py → tests\smoke.py(소스·빌드한 앱을 창 없이 띄워 API·첫 화면 + Playwright 스크린샷), 맥 zip 아티팩트
prompts\*.md      base(공통 규칙·뻔한 표현 목록) + 플랫폼별. platforms.json · templates.json
make_icon.py      app.ico · icon.png(180) 만들기     build.py  윈도우 한 파일 exe · 맥 .app(+zip)     release.py  빌드→태그→GitHub 릴리스·exe 첨부(맥 zip 은 아직 — ARCHITECTURE 8절)
tests\            test_gen · test_store · test_qr · test_ai(가짜 CLI·가짜 Ollama 서버 — 진짜 AI 안 부름) (unittest) · smoke.py(CI 스모크, unittest 가 안 줍는다)
```

데이터(앱이 쓰는 것, 저장소 밖): 기본 `%APPDATA%\PostKit\`(config.json · voice\ · posts\<날짜-메모>\{memo.txt, photos\, order.json, <플랫폼>.md, .history.jsonl, campaign.txt} · campaigns.json · ledger.json). 옮겼으면 `%APPDATA%\PostKit\location.json` 이 새 자리를 가리킨다. 로그·자동 백업은 `%LOCALAPPDATA%\PostKit\`(app.log · backups\). 맥은 `~/Library/Application Support/PostKit`(데이터) · `…/PostKit-local/backups` · `~/Library/Logs/PostKit/app.log`.

## 다른 PC 에서 이어 하기

```
git clone https://github.com/smh86278-stack/swbins-kit2.git C:\swbins-kit2      (private — smh86278-stack 로그인)
python -m pip install pillow pyinstaller                                        (파이썬 3.10+)
cd C:\swbins-kit2 && claude                                                     (이 파일을 읽고 이어 감)
```
앱 데이터(말투·글·장부)는 git 에 없다 — 데이터 폴더를 OneDrive 로 옮겨 두었으면 새 PC 앱의 ⚙️ 설정에서 같은 폴더를 고르면 된다.

## 규칙

- **회사 값 금지** — `C:\swbins2`(회사 일)·`C:\swbins-kit` 과 별개 저장소. 회사 이름·주소·계정이 코드·문서에 들어가면 안 된다. 개인 정보(블로그 주소·아이 실명 등)도 앱 데이터에만, 저장소엔 넣지 않는다.
- **발행 자동화 금지** — 네이버 글쓰기 창을 자동으로 채우거나 발행 버튼을 누르는 코드, 로그인 자동화, 여러 계정 돌리기는 만들지 않는다. "글쓰기 창 열어 주기 + 클립보드 복사" 까지만. 인스타·틱톡 공식 API 업로드는 DESIGN.md §9 에 설계만.
- **AI 연결은 CLI 로그인·로컬 Ollama 만**(API 키·토큰을 읽거나 저장하지 않는다). 프롬프트는 stdin 으로, 파일·명령은 못 건드리게:
  claude `--allowedTools Read`(사진 보기용), Bash·Write·웹 도구는 `--disallowedTools` · codex `exec --sandbox read-only`, 사진은 `--image` ·
  gemini `-p … --approval-mode default -o text`(헤드리스에선 쓰기·명령 도구가 빠지고 read_file 로 사진을 연다) · Ollama 는 `127.0.0.1:11434` 고정, 비전 모델(/api/show capabilities)일 때만 사진을 base64 로.
  사진을 못 보는 AI 면 메모만으로 쓰고 카드에 알린다(사진뿐이면 막음 — `app.photo_plan`). 세션 이어받기는 claude 만.
- **화면은 `127.0.0.1` 에만** — POST 는 띄울 때마다 새로 만드는 토큰(X-Token). 예외는 「폰에서 쓰기」를 켰을 때의 PhoneHandler 하나(PIN·세션·PC 전용 길 차단 `PHONE_ONLY_PC`). 새 API 를 만들면 폰에서 막아야 하는지 꼭 따진다.
- 답변·주석·화면 문구는 한국어(사용자에게 영어로 새지 말 것). "매크로" 대신 "자동화". 화면 말투는 "~해요", 안내 문장은 짧게.
- 디자인(2026-10-23, 「AI 스럽다」는 걱정으로 키트와 같은 방향으로 바꿈): 무채색 바탕 + 강조색 하나 + 선 아이콘, 그라데이션·이모지 탭 없음.
  기능·API·요소 id 는 시험·데모 스크립트가 기대하니 겉을 바꿀 때도 그대로 둔다(`nav button[data-tab]`·`.card .st`·`.camp [data-act]`·`#go` 등).
- 라이선스: 판매 예정 private 이라 LICENSE 파일 없음, README 에 "All rights reserved"(키트는 MIT 로 다름).
- 빌드 결과(`dist\`·`build\`)·`*.spec` 은 git 에 넣지 않는다. `app.ico`·`icon.png` 는 넣는다.

## 시험 · 함정

- **시험 데이터는 `POSTKIT_DATA=<폴더>` 로 분리**(위치 기록·백업도 그 폴더로 간다). 그냥 띄우면 실제 데이터·실제 자동 백업을 건드린다 — 한 번 섞여서 지운 적 있음.
  `POSTKIT_DATA=... python -X utf8 -c "import app; app.PORT=8651; app.main()" --no-window` 로 띄우고 Playwright 로 연다(사용자 창을 잡지 않게).
- 앱은 창이 닫혀 `/api/ping` 신호가 45초 끊기면 스스로 끝난다 — 살았는지 볼 땐 `/api/state` 를 부른다(`/api/ping` 은 신호를 다시 켠다).
- 서버 코드(app.py)를 고치면 다시 띄워야 하고, ui.html 만 고치면 새로고침이면 된다.
- 띄워 둔 `DungiLog.exe` 가 있으면 빌드가 덮어쓰지 못한다 — `Get-Process DungiLog | Stop-Process` 후 빌드.
- ui.html: `[hidden]` 은 맨 위 `display:none !important` 규칙으로 이긴다(없으면 display 규칙에 덮인다).
- 회사망 PC 에선 **pip·파이썬 urllib 이 SSL 검사에 막힌다**(self signed) — 인증서 검사를 끄지 말고 의존성 없이 짠다(qr.py 가 그래서 자체 구현). curl·git 은 된다.
- 실제 claude 호출 시험은 한 번에 30초쯤, 사용량을 먹으니 꼭 필요한 것만. codex·gemini 도 마찬가지 — 자동 시험은 test_ai 의 가짜로.
- 맥에서 깨지는 게 있는지는 CI 로만 본다 — 결과는 `gh` 가 없으니 `git credential fill` 토큰으로 GitHub API(`actions/runs`·`jobs/<id>/logs`), 토큰은 화면·파일에 남기지 않는다.
  CLI 를 '없음'으로 만드는 시험은 PATH 만 비우면 안 된다 — `gen.extra_dirs`·`_login_shell_path` 도 비운다(test_ai `test_missing_cli`).
- `tests/smoke.py` 는 8650 에 이미 앱이 떠 있으면 멈춘다(실제 데이터 보호). 이 PC 에서 돌릴 땐 띄워 둔 둥이로그를 먼저 끈다.
- 이 PC(회사망) 기본 파이썬엔 Pillow 가 pip SSL 에 막혀 없다 — 사진 시험(PhotoTest)은 Pillow 가 없으면 **건너뛴다**(skip, 실패 아님). 전부 돌리려면 Pillow 있는 파이썬(이 PC: `C:\swbins2\tools\macro-hub\.venv\Scripts\python.exe`)으로 `-m unittest discover tests`.

## git · 릴리스

브랜치 `main` 하나, 원격 `origin` = github.com/smh86278-stack/swbins-kit2 (private). 원격 주소에 계정 이름을 넣어 둔다(`https://smh86278-stack@github.com/...`) — 이 PC 엔 정지된 옛 계정 자격 증명도 남아 있어서.
커밋 전 `python -m unittest discover tests` 가 통과해야 한다. 커밋 메시지는 한국어.

**릴리스**(exe 배포, 사용자가 "릴리스 올려 줘" 하면): 커밋 → 본문을 파일로 쓰고 `<Pillow·PyInstaller 있는 python> release.py vX.Y.Z notes.md` — 빌드 → 태그 push → GitHub API 릴리스 + `dist\DungiLog.exe` 첨부까지 한 번에(2026-10-23). 손으로 할 때 순서도 같다.
`gh` 가 없으면 토큰은 `git credential fill`(GCM)에서 꺼내 curl 에 바로 넘기고 **화면·파일에 남기지 않는다**. 릴리스 본문 JSON 은 명령줄로 넘기면 한글이 깨지니 파일로(`--data-binary @file`).
지금까지: v0.1.0(48af3fc) · v0.2.0(691e3e1) · v0.3.0(2026-10-23, AI 고르기 8b4ba06 — 빌드는 Pillow·PyInstaller 가 있는 `C:\swbins2\tools\macro-hub\.venv\Scripts\python.exe -X utf8 build.py`) · v0.4.0(2026-10-23, 새 디자인 6c8086f — release.py 로 처음 올림) · v0.4.1(2026-10-26, 사진 개수·복사 + 글쓰기 창·참고 글 4ec8182) · v0.4.2(같은 날, 올린 뒤 검수·일정·달력 .ics) · v0.4.3(같은 날, 썸네일·카드뉴스 83cf240) · v0.4.4(같은 날, 세금용 엑셀·떼인 세금 e1985e9).
