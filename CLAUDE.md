# swbins-kit2 — 글 도우미 (개인 부업용 글쓰기 응용프로그램)

사진·메모를 넣으면 블로그·카페·인스타·틱톡용 글을 **내 말투로** 써 주고 다듬어 주는 윈도우 응용프로그램(exe 하나).
**올리는 건 사람이 한다** — 자동 발행·자동 로그인·브라우저 조작은 이 저장소에 넣지 않는다(네이버 약관·계정 정지 위험, 2026-10-19 사용자 결정).

설계·작업 순서는 `DESIGN.md` 가 정본이다. 먼저 읽는다.

## 규칙

- **회사 값 금지** — `C:\swbins2`(사방넷·daou)·`C:\swbins-kit` 과 별개 저장소. 회사 이름·주소·계정이 코드·문서에 들어가면 안 된다. 개인 정보(내 블로그 주소 등)도 설정 파일(`%APPDATA%\PostKit\config.json`)에만 두고 저장소엔 넣지 않는다.
- **발행 자동화 금지** — 네이버 글쓰기 창을 자동으로 채우거나 발행 버튼을 누르는 코드, 로그인 자동화, 여러 계정 돌리기는 만들지 않는다. "글쓰기 창 열어 주기 + 클립보드 복사" 까지만.
- **AI 연결은 `claude -p` 로그인 방식만** — API 키 없음(사용자 결정). 판매판으로 바꿀 때 키 방식을 덧붙인다.
- **화면은 `127.0.0.1` 에만** 연다. 상태를 바꾸는 POST 는 띄울 때마다 새로 만드는 토큰을 화면에 심어 확인한다(`swbins2\tools\dispatch-chat\chat.py` 방식).
- claude 에 허용하는 도구는 **Read 만**(사진 보기용). Bash·Write·브라우저 도구는 `--disallowedTools`.
- 답변·주석·화면 문구는 한국어. "매크로" 라는 말은 쓰지 않는다(폴더·exe 이름은 상관없음).
- 빌드 결과(`dist\`·`build\`)·`*.spec` 은 git 에 넣지 않는다.

## git

브랜치 `main` 하나, 원격 `origin` = github.com/smh86278-stack/swbins-kit2 (private).
커밋 전 `python -m unittest discover tests` 가 통과해야 한다.

## 검증 습관

```
python app.py            창이 뜨고(Edge --app), 사진 폴더 하나로 네이버 블로그 글이 나오는지
python build.py          dist\PostKit.exe 가 만들어지고 더블클릭으로 같은 동작
python -m unittest discover tests
```
