# 글 도우미 — 설계 · Opus 작업 지시서

작성 2026-10-19 (Fable 세션). 구현은 Opus 세션이 이 문서 순서대로 한다. 끝낸 항목은 이 문서의 체크박스를 채운다.

## 0. 한 줄 정의

> 사진 몇 장과 짧은 메모를 넣으면, 고른 플랫폼에 맞는 글을 **내 말투로** 써 주고, 고쳐 달라는 대로 다듬어 주고, 복사해서 글쓰기 창을 열어 주는 윈도우 앱. 올리는 건 내가 한다.

사용자 결정(2026-10-19):
- 쓰는 사람: 일단 나만. `claude -p` 로그인 방식, API 키 없음.
- 플랫폼: 네이버 블로그 · 네이버 카페 · 인스타그램 · 틱톡. 다른 곳은 설정 파일로 덧붙일 수 있게만.
- 범위: **1단계(글 만들기·다듬기)만 구현**. 2단계(인스타·틱톡 공식 API 업로드)는 §9 설계 메모만.
- 응용프로그램(exe)으로.
- "AI 글로 잡힌다" 걱정 → 속이는 기능이 아니라 **내 글처럼 만드는 재료**(내 말투 학습 · 직접 겪은 구체 사실 · 뻔한 표현 걷어내기)로 푼다. 광고·AI 표시를 숨기는 기능은 만들지 않는다.

## 1. 구조 — `swbins2\tools\dispatch-chat` 틀을 그대로 빌린다

| 부분 | 방식 | 빌려올 곳 |
|---|---|---|
| 창 | 파이썬 로컬 HTTP 서버(127.0.0.1, 빈 포트 자동) + Edge `--app=` 창(없으면 기본 브라우저) | `chat.py` `main()`·`open_window` 부분 |
| 화면 | `ui.html` 한 장(바닐라 JS, 외부 CDN 없음) | `ui.html` 의 뼈대만 — 펫·메신저 기능은 가져오지 않는다 |
| AI | `claude -p --output-format json --permission-mode dontAsk --allowedTools Read --disallowedTools Bash,Write,Edit,WebFetch,WebSearch` + `--add-dir <글 폴더>` | `chat_runner.py` `claude_cmd()`·`args` 조립·결과 JSON 파싱(`CREATE_NO_WINDOW` 포함) |
| 저장 | `%APPDATA%\PostKit\` | `chat.py` 의 LOCALDATA 방식 |
| exe | PyInstaller `--onefile --noconsole` | `build.py` (펫·company.json 줄은 뺀다) |

파일:

```
C:\swbins-kit2\
  app.py            서버·창·라우팅 (200~400줄 목표)
  gen.py            프롬프트 조립 · claude 호출 · 결과 파싱 (화면과 무관, 테스트 대상)
  platforms.json    플랫폼 정의(§4)
  prompts\
    base.md         공통 규칙(말투·뻔한 표현 금지·사실만)
    naver_blog.md · naver_cafe.md · instagram.md · tiktok.md
  ui.html
  build.py
  tests\test_gen.py
  CLAUDE.md · DESIGN.md · README.md · .gitignore
```

데이터(`%APPDATA%\PostKit\`):

```
config.json                 { "voice_note": "...", "default_platforms": [...], "last_dir": "..." }
voice\*.txt                 내가 쓴 글(말투 학습 재료). 파일 하나 = 글 하나
posts\<YYYYMMDD-slug>\
  memo.txt                  내가 적은 메모
  photos\                   넣은 사진(원본 복사)
  <platform>.md             만든 글(최신)
  <platform>.history.jsonl  다듬은 이력 {ts, instruction, text, session_id}
```

## 2. 화면 (탭 셋, 왼쪽 세로 탭)

### ✍ 쓰기 (기본 탭)
1. **재료**: 사진 끌어다 놓기/파일 고르기(여러 장) · 메모 칸(한 줄도 됨: "을지로 OO집, 7천원, 웨이팅 20분, 김치찌개 짰음") · 글 제목 후보(비워도 됨)
2. **플랫폼 체크박스**(platforms.json 순서, 기본값은 config.default_platforms) · 「글 만들기」
3. **결과**: 플랫폼마다 카드 하나. 카드 안에 글 편집기(textarea, 직접 고쳐도 됨) · 「다듬기」 칸(자유 문장: "더 짧게", "반말로", "가격 얘기 앞으로") + 빠른 버튼(짧게/길게/캐주얼/정중하게/해시태그만 다시) · 「복사」 · 「글쓰기 창 열기」 · 「사진 폴더 열기」
4. 「글 만들기」는 플랫폼별로 **병렬** claude 호출(스레드), 카드마다 진행 표시. 한 플랫폼 실패해도 나머지는 보여 준다.
5. 「다듬기」는 그 카드의 `session_id` 로 `claude -p --resume` — 앞 대화를 이어 받아 "방금 글에서 ~만 바꿔" 가 통한다. 세션이 없거나 실패하면 현재 글 전문을 넣어 새로 부른다.

### 🗣 내 말투
- 내가 쓴 글 붙여넣기 → `voice\` 에 저장(목록·삭제). 3~10편 권장 문구.
- "말투 메모" 한 칸(예: "반말, 이모지 거의 안 씀, 문단 짧게, '~했어요' 체") → config.voice_note.
- 프롬프트엔 voice 글 중 **최근 5편, 각 1500자까지** 만 넣는다(토큰).

### 📂 지난 글
- `posts\` 목록(날짜·메모 첫 줄·플랫폼). 열면 ✍ 탭에 그대로 복원(다듬기 이어서 가능).

공통: 상단에 claude 상태(찾음/없음/로그인 필요 — `claude_cmd()` 결과와 첫 호출 오류로 판단). 없으면 설치 안내 링크.

## 3. 프롬프트 조립 (`gen.py build_prompt(platform, memo, title, photo_dir, voice_texts, voice_note)`)

순서: `prompts\base.md` → 플랫폼 md → 내 말투(voice_note + 글 예시) → 재료(메모·제목·사진 경로 목록: "폴더 안 사진을 Read 로 보고 글에 반영해라") → 출력 형식.

`base.md` 에 꼭 들어갈 것:
- 메모에 없는 사실(가격·날짜·효능·수치)을 **지어내지 않는다**. 모르면 `[확인: ~]` 로 표시.
- 뻔한 표현 금지 목록(예: "~에 대해 알아보겠습니다", "오늘은 ~를 소개해드릴게요", "완전 강추", "인생 맛집", "가성비 갑", 마지막 "다음에 또 ~로 찾아올게요"). 서론 없이 바로 장면·사실로 시작.
- 광고·협찬이면 메모에 적힌 대로 첫 줄에 표기 문구를 넣는다(메모에 `#협찬` 이 있으면).
- 출력은 글 본문만. 앞뒤 설명·마크다운 코드블록 없이.

플랫폼 md 는 길이·구성·해시태그 수·줄바꿈 습관만 담는다(§4 값과 중복 금지 — md 는 글 성격, json 은 숫자·URL).

사진은 `--add-dir` 로 글 폴더를 열어 주고 Read 만 허용. 사진이 10장 넘으면 앞 10장만(프롬프트에 알림).

## 4. `platforms.json`

```json
[
  {"id": "naver_blog", "name": "네이버 블로그", "prompt": "naver_blog.md",
   "length": "1500~2500자", "hashtags": 5, "write_url": "https://blog.naver.com/GoBlogWrite.naver", "enabled": true},
  {"id": "naver_cafe", "name": "네이버 카페", "prompt": "naver_cafe.md",
   "length": "600~1200자", "hashtags": 0, "write_url": "", "enabled": true},
  {"id": "instagram", "name": "인스타그램", "prompt": "instagram.md",
   "length": "300~600자", "hashtags": 15, "write_url": "https://www.instagram.com/", "enabled": true},
  {"id": "tiktok", "name": "틱톡", "prompt": "tiktok.md",
   "length": "캡션 150자 + 자막 대본 30초", "hashtags": 5, "write_url": "https://www.tiktok.com/upload", "enabled": true}
]
```

- 카페 `write_url` 은 카페마다 달라 비워 두고, config.json 에 `"write_urls": {"naver_cafe": "..."}` 로 덮어쓸 수 있게.
- 다른 플랫폼(스레드·X·유튜브 커뮤니티 등)은 여기 한 줄 + md 한 장으로 추가 — 코드 수정 없이.

## 5. `gen.py` 공개 함수 (테스트 대상)

```
find_claude() -> list[str] | None
build_prompt(platform: dict, memo, title, photo_names: list[str], voice_texts: list[str], voice_note: str) -> str
run(prompt, workdir, resume_id=None, timeout=180) -> {"text": str, "session_id": str, "error": str}
parse_result(stdout: str) -> dict      # json 한 덩어리 또는 마지막 json 줄 (chat_runner 의 파서 그대로)
new_post_dir(root, memo) -> str        # YYYYMMDD-<메모 앞 12자 안전화>, 겹치면 -2
```

안전: `post_dir`·`photo` 경로는 모두 `%APPDATA%\PostKit\posts` 아래인지 확인(`os.path.commonpath`). 화면에서 온 파일 경로는 복사만 하고 원본은 건드리지 않는다.

## 6. `app.py` 라우팅

| 길 | 일 |
|---|---|
| `GET /` | ui.html (토큰 심어서) |
| `GET /api/state` | claude 상태·플랫폼 목록·config·voice 목록 |
| `POST /api/post/new` | memo·title·사진(파일 경로 목록 — 화면에선 `<input type=file>` 로 고른 뒤 서버가 복사. 끌어놓기는 경로를 못 받으니 파일 내용을 multipart 로 올림) → post_dir |
| `POST /api/gen` | post_dir·platforms[] → 플랫폼별 스레드 시작, job id |
| `GET /api/job/<id>` | 플랫폼별 {status, text, error} |
| `POST /api/refine` | post_dir·platform·instruction·current_text → 결과(동기, 180초) |
| `POST /api/voice` · `DELETE /api/voice/<name>` | 말투 글 저장·삭제 |
| `POST /api/config` | voice_note·default_platforms·write_urls |
| `POST /api/open` | `{"what": "folder"|"write", "post_dir", "platform"}` → 탐색기 / 기본 브라우저로 write_url |
| `GET /api/posts` · `GET /api/posts/<dir>` | 지난 글 |

POST 는 전부 토큰(`X-Token` 헤더) 확인, Host 가 127.0.0.1:포트 인지 확인.

## 7. 빌드·배포

- `build.py`: dispatch-chat `build.py` 복사 → 이름 `PostKit`, add-data 는 `ui.html`·`platforms.json`·`prompts\*` 만. 아이콘은 선택(없으면 빼고 빌드).
- 실행 파일 안에서 자원 경로는 `sys._MEIPASS` 우선(`chat.py` 의 `C.RES` 방식).
- README.md: 설치(claude 로그인 한 번) → 사진·메모 → 플랫폼 → 복사 → 직접 올리기. "자동 발행은 일부러 없다" 한 줄과 이유.

## 8. 작업 순서 (Opus)

- [ ] 1. 뼈대: `.gitignore`(dist/ build/ *.spec __pycache__/), `platforms.json`, `prompts\` 5장, `gen.py` 의 `build_prompt`·`parse_result`·`new_post_dir` + `tests\test_gen.py`(프롬프트에 금지 표현 목록·사진 이름·말투 예시가 들어가는지, 경로 안전, json 파싱 3종)
- [ ] 2. `gen.py run()` — 실제 `claude -p` 호출. 사진 폴더 하나로 네이버 블로그 글이 나오는지 손으로 확인(결과를 README 에 붙이지 말 것 — 개인 정보).
- [ ] 3. `app.py` + `ui.html` ✍ 탭(재료 → 글 만들기 → 카드 → 다듬기 → 복사/창 열기)
- [ ] 4. 🗣 내 말투 · 📂 지난 글 탭
- [ ] 5. `build.py` → `dist\PostKit.exe` 더블클릭 확인
- [ ] 6. README · 첫 커밋 · `git push origin main`

각 단계 끝에 `python -m unittest discover tests`. 3단계부터는 전용 창으로 시험한다(사용자 메모장·브라우저 창을 잡지 않는다).

## 9. 2단계 설계 메모 — 공식 API 업로드 (구현하지 않음)

| 플랫폼 | 길 | 준비물 | 제약 |
|---|---|---|---|
| 인스타그램 | Instagram Graph API — `POST /{ig-user-id}/media` (image_url 또는 carousel) → `POST /{ig-user-id}/media_publish` | Meta 개발자 앱 · 비즈니스/크리에이터 계정 · 페이스북 페이지 연결 · 장기 토큰(60일, 갱신 필요) | 사진이 **공개 URL** 이어야 함 → 임시 올릴 곳(S3·R2·GitHub Pages 등) 필요. 하루 게시 한도 25건 |
| 틱톡 | Content Posting API — Direct Post (`/v2/post/publish/video/init/` + 파일 업로드) | 틱톡 개발자 앱 · `video.publish` 권한 · OAuth | **앱 심사 전엔 나만 보기(SELF_ONLY)로만** 올라감. 심사엔 앱 설명·시연 영상 필요 |
| 네이버 블로그·카페 | 공식 글쓰기 API 없음(블로그 API 종료) | — | **만들지 않는다**(약관·계정 정지). 지금처럼 복사+창 열기 |

구조는 `platforms.json` 에 `"publish": {"type": "instagram_graph" | "tiktok_direct"}` 를 더하고, `publish.py` 에 플랫폼별 클래스. 토큰은 config.json 이 아니라 **DPAPI 로 감싼 별도 파일**(dispatch-chat 의 비밀번호 저장 방식). 「올리기」 단추는 항상 글을 한 번 더 보여 주고 확인을 받은 뒤 동작. 예약 올리기는 허브(`swbins-kit`) `job_*` 로 붙일 수 있다.

## 10. 판매판으로 갈 때 (메모)

- AI 연결: 구매자 자기 API 키(Anthropic) 입력 칸 + `gen.py` 에 `run_api()` 추가(claude -p 와 같은 결과 형식). 개인 구독 `claude -p` 를 남의 서비스에 돌리면 약관 위반.
- AI 기본법(2026-01 시행) 생성물 표시 의무 확인 · 협찬 글 표기 안내를 화면에 고정.
