# -*- coding: utf-8 -*-
"""AI 고르기 — 가짜 CLI(claude·codex·gemini)와 가짜 Ollama 서버로만 시험한다. 진짜 AI 는 부르지 않는다(비용)."""
import base64
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
DATA = tempfile.mkdtemp(prefix="postkit-ai-data-")
os.environ["POSTKIT_DATA"] = DATA          # app 을 불러도 실제 데이터·자동 백업을 건드리지 않게(불러오기 전에)
import ai  # noqa: E402
import app  # noqa: E402
import gen  # noqa: E402

BLOG = {"id": "naver_blog", "name": "네이버 블로그", "prompt": "naver_blog.md", "length": "1500자", "hashtags": 10, "title": True}

# 가짜 CLI — 받은 인자·작업 폴더·표준 입력을 log.json 에 남기고, 엔진마다 진짜처럼 답한다
FAKE = r'''
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")      # 진짜 CLI(node)처럼 UTF-8 로 낸다
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
name = sys.argv[1]; args = sys.argv[2:]
stdin = sys.stdin.buffer.read().decode("utf-8")
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), name + ".log.json"), "w", encoding="utf-8") as f:
    json.dump({"args": args, "cwd": os.getcwd(), "stdin": stdin}, f, ensure_ascii=False)
if os.environ.get("FAKE_FAIL") == name:
    sys.stderr.write("로그인이 필요합니다"); sys.exit(3)
if name == "claude":
    print(json.dumps({"type": "result", "subtype": "success", "result": "클로드 글", "session_id": "sess-1"}, ensure_ascii=False))
elif name == "codex":
    out = args[args.index("-o") + 1]
    with open(out, "w", encoding="utf-8") as f:
        f.write("코덱스 글")
    print("진행 기록(무시됨)")
else:
    sys.stdout.buffer.write("```\n제미나이 글\n```\n".encode("utf-8"))
'''


class FakeOllama(http.server.BaseHTTPRequestHandler):
    models = {"qwen3:8b": [], "gemma3:4b": ["vision"]}
    last = {}

    def log_message(self, *a):
        pass

    def _send(self, code, d):
        b = json.dumps(d).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/api/tags":
            return self._send(200, {"models": [{"name": n} for n in self.models]})
        self._send(404, {"error": "없음"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
        if body.get("model") not in self.models:
            return self._send(404, {"error": "model not found"})
        if self.path == "/api/show":
            return self._send(200, {"capabilities": ["completion"] + self.models[body["model"]]})
        if self.path == "/api/chat":
            FakeOllama.last = body
            return self._send(200, {"message": {"role": "assistant", "content": "<think>생각</think>\n올라마 글"}, "done": True})
        self._send(404, {"error": "없음"})


def setUpModule():
    global BIN, SERVER, OLD_PATH, OLD_URL
    BIN = tempfile.mkdtemp(prefix="postkit-fakebin-")
    with open(os.path.join(BIN, "fake.py"), "w", encoding="utf-8") as f:
        f.write(FAKE)
    for name in ("claude", "codex", "gemini"):
        if os.name == "nt":
            with open(os.path.join(BIN, name + ".cmd"), "w", encoding="ascii") as f:
                f.write('@"%s" "%%~dp0fake.py" %s %%*\r\n' % (sys.executable, name))
        else:
            p = os.path.join(BIN, name)
            with open(p, "w") as f:
                f.write('#!/bin/sh\nexec "%s" "%s/fake.py" %s "$@"\n' % (sys.executable, BIN, name))
            os.chmod(p, 0o755)
    OLD_PATH = os.environ["PATH"]
    os.environ["PATH"] = BIN + os.pathsep + OLD_PATH          # 진짜 claude·codex·gemini 보다 먼저 찾히게
    SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=SERVER.serve_forever, daemon=True).start()
    OLD_URL = ai.OLLAMA_URL
    ai.OLLAMA_URL = "http://127.0.0.1:%d" % SERVER.server_address[1]


def tearDownModule():
    SERVER.shutdown()
    os.environ["PATH"] = OLD_PATH
    ai.OLLAMA_URL = OLD_URL
    shutil.rmtree(BIN, ignore_errors=True)
    shutil.rmtree(DATA, ignore_errors=True)


def fake_log(name):
    with open(os.path.join(BIN, name + ".log.json"), encoding="utf-8") as f:
        return json.load(f)


def make_post(memo="을지로 김치찌개 7천원", photos=("a.jpg",)):
    d = gen.new_post_dir(os.path.join(DATA, "posts"), memo or "사진")
    with open(os.path.join(d, "memo.txt"), "w", encoding="utf-8") as f:
        f.write(memo)
    for n in photos:
        with open(os.path.join(d, "photos", n), "wb") as f:
            f.write(b"JPEGDATA-" + n.encode())
    return d


def S(engine, model=""):
    return ai.settings({"ai": {"engine": engine, "models": {engine: model} if model else {}}})


class SettingsTest(unittest.TestCase):
    def test_default_is_claude(self):
        self.assertEqual(ai.settings({})["engine"], "claude")
        self.assertEqual(ai.settings({"ai": {"engine": "누구"}})["engine"], "claude")
        self.assertEqual(ai.model_of(S("ollama")), "qwen3:8b")
        self.assertEqual(ai.model_of(S("codex")), "")

    def test_clean_settings_drops_odd_values(self):
        s = ai.clean_settings({"engine": "gemini", "models": {"gemini": "gemini-2.5-pro", "ollama": "a b; rm", "zzz": "x"}, "token": "비밀"})
        self.assertEqual(s, {"engine": "gemini", "models": {"gemini": "gemini-2.5-pro"}})      # 모르는 키(토큰 등)는 저장 안 함

    def test_photo_mode_per_engine(self):
        self.assertEqual(ai.photo_mode(S("claude")), "Read")
        self.assertEqual(ai.photo_mode(S("codex")), "attached")
        self.assertEqual(ai.photo_mode(S("gemini")), "read_file")
        self.assertEqual(ai.photo_mode(S("ollama")), "none")                  # qwen3 는 글 전용
        self.assertEqual(ai.photo_mode(S("ollama", "gemma3:4b")), "attached")

    def test_prompt_photo_modes(self):
        none = gen.build_prompt(BLOG, "m", "", ["a.jpg"], [], "", photo_mode="none")
        self.assertIn("볼 수 없다", none)
        self.assertNotIn("./photos/a.jpg", none)
        self.assertIn("붙어 있다", gen.build_prompt(BLOG, "m", "", ["a.jpg"], [], "", photo_mode="attached"))
        self.assertIn("read_file 로 열어", gen.build_prompt(BLOG, "m", "", ["a.jpg"], [], "", photo_mode="read_file"))
        self.assertIn("Read 로 열어", gen.build_prompt(BLOG, "m", "", ["a.jpg"], [], ""))   # 기본은 지금까지 그대로


class CliTest(unittest.TestCase):
    def test_status_finds_fake_clis(self):
        st = ai.status({"ai": {"engine": "codex"}})
        rows = {r["id"]: r for r in st["engines"]}
        self.assertTrue(rows["codex"]["installed"] and rows["gemini"]["installed"] and rows["claude"]["installed"])
        self.assertTrue(rows["ollama"]["installed"])
        self.assertFalse(rows["ollama"]["vision"])
        self.assertTrue(st["ready"])
        self.assertEqual(ai.status({}, full=False)["engines"], [])

    def test_claude_passes_model_and_session(self):
        d = make_post()
        r = ai.run(S("claude", "sonnet"), "프롬프트", d, resume_id="old")
        self.assertEqual((r["text"], r["session_id"]), ("클로드 글", "sess-1"))
        a = fake_log("claude")["args"]
        self.assertIn("Read", a)
        self.assertEqual(a[a.index("--model") + 1], "sonnet")
        self.assertEqual(a[a.index("--resume") + 1], "old")

    def test_codex_read_only_with_images(self):
        d = make_post(photos=("a.jpg", "b.png"))
        r = ai.run(S("codex", "gpt-5"), "블로그 글 써 줘", d, photos=["b.png", "a.jpg"])
        self.assertEqual(r, {"text": "코덱스 글", "session_id": "", "error": ""})
        log = fake_log("codex")
        a = log["args"]
        self.assertEqual(a[0], "exec")
        self.assertEqual(a[a.index("--sandbox") + 1], "read-only")
        self.assertEqual(a[a.index("-m") + 1], "gpt-5")
        self.assertEqual(a[a.index("--image") + 1:], [os.path.join(d, "photos", "b.png"), os.path.join(d, "photos", "a.jpg")])
        self.assertEqual(log["stdin"], "블로그 글 써 줘")

    def test_gemini_runs_in_post_folder_readonly(self):
        d = make_post()
        r = ai.run(S("gemini"), "글 써 줘", d)
        self.assertEqual(r["text"], "제미나이 글")                            # 감싼 코드블록 벗김
        log = fake_log("gemini")
        self.assertEqual(log["args"][log["args"].index("--approval-mode") + 1], "default")
        self.assertIn("text", log["args"])
        self.assertNotIn("-m", log["args"])
        self.assertEqual(os.path.realpath(log["cwd"]), os.path.realpath(d))   # read_file 로 ./photos 를 열 수 있게
        self.assertEqual(log["stdin"], "글 써 줘")

    def test_cli_failure_message(self):
        os.environ["FAKE_FAIL"] = "codex"
        try:
            r = ai.run(S("codex"), "p", make_post())
        finally:
            del os.environ["FAKE_FAIL"]
        self.assertEqual(r["text"], "")
        self.assertIn("로그인이 필요합니다", r["error"])

    def test_missing_cli(self):
        old = os.environ["PATH"]
        os.environ["PATH"] = BIN + "-없음"
        try:
            self.assertIn("npm install -g @openai/codex", ai.not_ready(S("codex")))
            self.assertIn("찾지 못했어요", ai.run(S("gemini"), "p", DATA)["error"])
        finally:
            os.environ["PATH"] = old


class OllamaTest(unittest.TestCase):
    def test_text_model_no_images(self):
        r = ai.run(S("ollama"), "글 써 줘", make_post(), photos=[])
        self.assertEqual(r["text"], "올라마 글")                              # <think> 는 지운다
        self.assertEqual(FakeOllama.last["model"], "qwen3:8b")
        self.assertNotIn("images", FakeOllama.last["messages"][0])

    def test_vision_model_gets_images(self):
        d = make_post(photos=("a.jpg",))
        ai.run(S("ollama", "gemma3:4b"), "p", d, photos=["a.jpg"])
        self.assertEqual(FakeOllama.last["messages"][0]["images"], [base64.b64encode(b"JPEGDATA-a.jpg").decode()])

    def test_missing_model_and_server_down(self):
        self.assertIn("ollama pull llava", ai.not_ready(S("ollama", "llava")))
        self.assertIn("ollama pull llava", ai.run(S("ollama", "llava"), "p", DATA)["error"])
        old = ai.OLLAMA_URL
        ai.OLLAMA_URL = "http://127.0.0.1:9"                                    # 아무도 없는 자리
        try:
            self.assertIn("꺼져 있거나", ai.not_ready(S("ollama")))
            self.assertIsNone(ai.ollama_models())
            self.assertIn("연결하지 못했어요", ai.run(S("ollama"), "p", DATA, timeout=2)["error"])
        finally:
            ai.OLLAMA_URL = old


class AppTest(unittest.TestCase):
    """앱 쪽 — 사진을 못 보는 AI 면 메모만으로 쓰고 알리거나, 사진뿐이면 막는다. 다듬기는 claude 만 이어받는다."""

    def set_ai(self, engine, model=""):
        cfg = app.load_cfg()
        cfg["ai"] = {"engine": engine, "models": {engine: model} if model else {}}
        os.makedirs(app.DATA, exist_ok=True)
        app.write_text(app.CFG, json.dumps(cfg, ensure_ascii=False))

    def wait(self, job):
        for _ in range(100):
            with app.LOCK:
                j = dict(app.JOBS[job])
            if all(v["status"] != "running" for v in j.values()):
                return j
            time.sleep(0.1)
        self.fail("작업이 끝나지 않음")

    def test_text_model_writes_from_memo_with_note(self):
        self.set_ai("ollama")
        d = make_post()
        j = self.wait(app.start_gen(d, ["naver_blog"]))["naver_blog"]
        self.assertEqual(j["status"], "done")
        self.assertIn("메모만으로", j["note"])
        self.assertIn("볼 수 없다", FakeOllama.last["messages"][0]["content"])
        rows = app.history(d, "naver_blog")
        self.assertEqual(rows[-1]["engine"], "ollama")

    def test_photo_only_blocked_for_text_model(self):
        self.set_ai("ollama")
        with self.assertRaises(ValueError):
            app.start_gen(make_post(memo=""), ["naver_blog"])
        self.set_ai("ollama", "gemma3:4b")                                      # 비전 모델이면 된다
        j = self.wait(app.start_gen(make_post(memo=""), ["naver_blog"]))["naver_blog"]
        self.assertEqual((j["status"], j["note"]), ("done", ""))
        self.assertIn("images", FakeOllama.last["messages"][0])

    def test_refine_resumes_only_claude_sessions(self):
        d = make_post()
        app.save_result(d, "naver_blog", "앞 글", "sess-old", "", "claude")
        self.set_ai("codex")
        r = app.refine(d, app.platform("naver_blog"), "더 짧게", "앞 글")
        self.assertEqual(r["text"].splitlines()[0], "코덱스 글")
        self.assertIn("<지금 글>", fake_log("codex")["stdin"])               # 세션 없이 지금 글을 붙여 새로
        self.set_ai("claude")
        app.refine(d, app.platform("naver_blog"), "더 짧게", "코덱스 글")
        a = fake_log("claude")["args"]
        self.assertEqual(a[a.index("--resume") + 1], "sess-old")               # 그 앞 claude 세션에 이어(지금 글은 프롬프트에)


if __name__ == "__main__":
    unittest.main()
