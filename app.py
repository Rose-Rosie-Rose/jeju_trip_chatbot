"""
Jeju Chatbot — Gradio UI
Figma: "jeju chatbot - palette (sand)" (node 1062:404)

구성
  app.py               UI 구성과 이벤트 연결 (백엔드는 이 파일만 보면 됩니다)
  requirements.txt
  assets/
    strings.json       화면에 보이는 모든 문구 (en / ko)
    tokens.css         디자인 토큰 (색, 크기, 그림자, 모션)
    app.css            토큰을 사용하는 컴포넌트 스타일과 애니메이션
    effects.js         버튼 리플 같은 인터랙션 (CSS만으로 안 되는 부분)
    icons/             Figma에서 추출한 아이콘

실행
  pip install -r requirements.txt
  python app.py                  # 기본 언어: 영어(en) — strings.json 의 default_locale
  APP_LOCALE=ko python app.py    # 한국어로 실행 (Windows PowerShell: $env:APP_LOCALE="ko"; python app.py)

===========================================================================
백엔드 연동 가이드 (요약)
===========================================================================
1) 모델을 붙이는 곳은 단 한 곳: generate_reply(message, history)
   - message : 방금 사용자가 보낸 문장 (str, 앞뒤 공백 제거됨)
   - history : 이번 메시지 "이전"까지의 대화 (list[ChatMessage]), 첫 항목은 인사말
   - 반환     : 문자열 조각을 yield (스트리밍). 한 번에 보내려면 전체 답변을 한 번만 yield.
   - 예외     : 여기서 예외가 나면 화면에 S["chat"]["error"] 문구가 대신 표시됩니다.

2) 대화 기록 형식 (OpenAI messages 형식과 동일 → 그대로 API에 넘겨도 됩니다)
     [{"role": "assistant", "content": "Hello there! ..."},
      {"role": "user",      "content": "제주 맛집 추천해줘"}]
   - role 은 "user" 또는 "assistant" 만 사용합니다. system 프롬프트는 generate_reply 안에서 앞에 붙이세요.
   - content 는 항상 str 로 정리해서 넘겨드립니다(message_text 참고). 마크다운 사용 가능(**굵게**, 목록, 링크).

3) 화면 문구는 코드에 직접 쓰지 말고 S[...] 를 쓰세요 (assets/strings.json).
     S["chat"]["greeting"]         첫 인사말 / 새 대화 시 인사말
     S["chat"]["error"]            모델 오류 시 말풍선 문구
     S["composer"]["placeholder"]  입력창 안내 문구
     S["composer"]["empty_warning"] 빈 메시지 전송 시 토스트
   새 문구가 필요하면 strings.json 의 en / ko 양쪽에 같은 키로 추가하세요.

4) 대화 기록은 브라우저 세션(탭)별로 Gradio 가 들고 있습니다(서버 DB 없음).
   사용자/세션 구분이 필요하면 stream_bot 에 request: gr.Request 인자를 추가하세요(함수 주석 참고).
===========================================================================
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import threading
from pathlib import Path
from typing import Iterator, Literal, TypedDict

import gradio as gr

import test_pdf as rag

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 경로 상수
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent   # 이 파일이 있는 폴더 (실행 위치와 무관)
ASSETS = BASE_DIR / "assets"                 # strings.json, css, js
ICONS = ASSETS / "icons"                     # svg / png 아이콘


# ---------------------------------------------------------------------------
# 타입 — 백엔드와 주고받는 메시지 형태
# ---------------------------------------------------------------------------
class ChatMessage(TypedDict):
    """대화 한 줄. gr.Chatbot 의 값(list[ChatMessage])과 같은 형태입니다."""

    role: Literal["user", "assistant"]
    content: str  # 마크다운 문자열


History = list[ChatMessage]


# ---------------------------------------------------------------------------
# 문구 (assets/strings.json)
# ---------------------------------------------------------------------------
FALLBACK_LOCALE = "en"  # strings.json 에 default_locale 이 없을 때 쓰는 기본값


def load_strings(locale: str | None = None) -> dict:
    """현재 언어의 문구 묶음(dict)을 돌려줍니다.

    언어 결정 순서: 인자 locale → 환경변수 APP_LOCALE → strings.json 의 default_locale("en")
    없는 언어 코드가 오면 default_locale 로 대체합니다.
    """
    data = json.loads((ASSETS / "strings.json").read_text(encoding="utf-8"))
    default = data.get("default_locale", FALLBACK_LOCALE)
    locale = locale or os.getenv("APP_LOCALE") or default
    if locale not in data["locales"]:
        locale = default
    return data["locales"][locale]


# S: 화면 문구 사전. 예) S["chat"]["greeting"], S["nav"]["profile"]
#    키 구조는 assets/strings.json 의 locales.en 을 그대로 따릅니다.
S: dict = load_strings()


# ---------------------------------------------------------------------------
# 아이콘 → CSS 변수 (data URI)  ※ 프론트 전용, 백엔드는 수정할 필요 없음
# CSS 파일에서는 var(--icon-send) 처럼 쓰고, 실제 파일은 assets/icons/ 에서 관리합니다.
# 경로 문제(root_path, 프록시 등) 없이 어디서든 동작하도록 data URI로 넣습니다.
# ---------------------------------------------------------------------------
ICON_FILES = {
    "send": "send.png",
    "copy": "copy.svg",
    "new-chat": "header_chat.svg",
    "online": "online.svg",
    "nav-chatbot": "nav_chatbot.svg",
    "nav-profile": "nav_profile.svg",
}


def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if path.suffix == ".svg":
        mime = "image/svg+xml"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def icon_css_vars() -> str:
    lines = [f'  --icon-{name}: url("{_data_uri(ICONS / file)}");' for name, file in ICON_FILES.items()]
    return ":root {\n" + "\n".join(lines) + "\n}\n"


def build_css() -> str:
    # 순서: 토큰 → 아이콘 변수 → 컴포넌트 스타일
    return "\n".join(
        [
            (ASSETS / "tokens.css").read_text(encoding="utf-8"),
            icon_css_vars(),
            (ASSETS / "app.css").read_text(encoding="utf-8"),
        ]
    )


def build_head() -> str:
    # 접근성 라벨 등 JS에서 쓰는 문구를 strings.json 에서 그대로 전달 (window.APP_STRINGS)
    strings_js = json.dumps(S, ensure_ascii=False).replace("</", "<\\/")
    return FONT_HEAD + f"<script>window.APP_STRINGS = {strings_js};</script>"


FONT_HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
"""


# ===========================================================================
# ★ 백엔드 연결 지점 ★
# ===========================================================================
def generate_reply(message: str, history: History) -> Iterator[str]:
    """사용자 메시지에 대한 봇 답변을 만듭니다.

    test_pdf.py 의 RAG 파이프라인을 사용합니다.
      검색(영어 질문 + 한국어 번역 질문) → 답변 생성(영어) → 실제 사용한 PDF·페이지를 출처로 덧붙임
    현재는 이번 질문만으로 검색·답변하며, history 는 사용하지 않습니다.

    Args:
        message: 사용자가 방금 보낸 문장 (공백 제거된 str, 빈 문자열은 들어오지 않음)
        history: message 이전까지의 대화 기록 (list[ChatMessage]).
                 마지막 항목이 바로 이 message 입니다 → API 에는 history 를 그대로 넘기면 됩니다.

    Yields:
        답변 문자열 조각. yield 할 때마다 화면 말풍선 뒤에 이어 붙습니다.
        스트리밍이 필요 없으면 완성된 답변을 한 번만 yield 하세요.

    Raises:
        어떤 예외든 stream_bot 이 잡아서 S["chat"]["error"] 를 대신 보여줍니다.
        (오류 원인은 서버 로그로 남기세요.)

    예) OpenAI 호환 API (스트리밍)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
        stream = client.chat.completions.create(model=MODEL, messages=messages, stream=True)
        for chunk in stream:
            yield chunk.choices[0].delta.content or ""

    예) RAG 파이프라인 (한 번에 반환)
        docs = retriever.search(message, k=4)
        yield rag_chain.invoke({"question": message, "context": docs, "history": history})
    """
    try:
        docs = rag.retrieve(get_db(), message)
        if not docs:
            yield rag.NOT_FOUND
            return

        answer, used_docs = rag.answer_in_english(message, docs)
    except Exception:
        logger.exception("RAG 답변 생성 실패: %s", message)
        raise

    yield answer
    if used_docs:
        yield "\n\n" + format_sources_md(used_docs)


# ---------------------------------------------------------------------------
# RAG 벡터 DB / 출처 표시
# ---------------------------------------------------------------------------
_db = None
_db_lock = threading.Lock()


def get_db():
    """data/pdfs 의 PDF로 만든 벡터 DB. 처음 한 번만 만들고 이후에는 재사용합니다."""
    global _db
    with _db_lock:
        if _db is None:
            if not rag.PDF_PATHS:
                raise FileNotFoundError(f"PDF 폴더에 PDF 파일이 없습니다: {rag.PDF_DIR}")
            _db = rag.build_vector_db()
    return _db


def format_sources_md(docs) -> str:
    """실제 답변에 사용한 PDF·페이지를 마크다운 목록으로 만듭니다.

    예)
    **Sources**
    - Jeju Food Guide (jjfood.pdf) — pages 13–15
    """
    by_pdf: dict[tuple[str, str], list[int]] = {}
    for doc in docs:
        by_pdf.setdefault((rag.pdf_title(doc), rag.pdf_file(doc)), []).append(rag.page_no(doc))

    lines = [f'**{S["chat"]["sources"]}**']
    for (title, filename), pages in sorted(by_pdf.items()):
        lines.append(f"- {title} ({filename}) — {rag._format_pages(pages)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 대화 흐름 (보통 수정할 필요 없음)
# ---------------------------------------------------------------------------
def message_text(content) -> str:
    """Gradio 6은 content 를 [{"type": "text", "text": ...}] 형태로 돌려줄 때가 있어 str 로 통일합니다."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return content.get("text", "")
    if isinstance(content, (list, tuple)):
        return "".join(message_text(c) for c in content)
    return str(content or "")


def initial_history() -> History:
    """첫 화면 / '새 대화' 버튼을 눌렀을 때의 대화 기록 (인사말 1개)."""
    return [{"role": "assistant", "content": S["chat"]["greeting"]}]


def add_user_message(message: str, history: History):
    """1단계: 입력창 문장을 대화에 추가하고 입력창을 비웁니다.

    Returns: (입력창 새 값, 새 대화 기록)
    """
    message = (message or "").strip()
    if not message:
        gr.Warning(S["composer"]["empty_warning"])
        return gr.update(), history
    history = history + [{"role": "user", "content": message}]
    return "", history


def stream_bot(history: History):
    """2단계: generate_reply 결과를 받아 마지막 봇 말풍선을 점점 채웁니다.

    yield 할 때마다 gr.Chatbot 이 다시 그려집니다(스트리밍 표시).

    세션/사용자 정보가 필요하면 인자를 이렇게 바꾸세요 (Gradio 가 자동으로 넣어줍니다):
        def stream_bot(history: History, request: gr.Request):
            session_id = request.session_hash       # 브라우저 탭마다 고유
            client_ip  = request.client.host
    """
    if not history or history[-1]["role"] != "user":
        yield history
        return
    history = [{"role": m["role"], "content": message_text(m["content"])} for m in history]
    user_msg = history[-1]["content"]
    history = history + [{"role": "assistant", "content": ""}]
    try:
        for piece in generate_reply(user_msg, history[:-1]):
            history[-1]["content"] += piece
            yield history
    except Exception:  # 모델 오류 시 말풍선에 안내 문구 (원인은 generate_reply 안에서 로깅 권장)
        history[-1]["content"] = S["chat"]["error"]
        yield history


# ---------------------------------------------------------------------------
# 하단 Profile 탭 (프론트 전용)
# 프로필 화면이 아직 없어서, 누르면 브라우저 알림창만 띄우고 Chatbot 탭에 그대로 머뭅니다.
# 서버를 거치지 않는 순수 JS 라 응답이 즉시 뜹니다. 문구: S["profile"]["alert"]
# 나중에 프로필 화면을 만들면 이 JS 대신 화면 전환 함수를 연결하세요.
# ---------------------------------------------------------------------------
PROFILE_ALERT_JS = """
() => {
  const s = (window.APP_STRINGS && window.APP_STRINGS.profile) || {};
  window.alert(s.alert || "Coming soon");
  const input = document.querySelector("#composer-input textarea");
  if (input) input.focus();               // 알림을 닫으면 바로 다시 입력할 수 있게
}
"""


# ===========================================================================
# UI
# 아래 변수들은 이벤트 연결에 쓰는 Gradio 컴포넌트입니다.
#   chatbot          gr.Chatbot  값 = History (list[ChatMessage])  ← 대화 기록 전체
#   msg              gr.Textbox  값 = str                          ← 입력창
#   send_btn         gr.Button   전송 버튼 (답변 중에는 잠김)
#   new_chat_btn     gr.Button   헤더 오른쪽 '새 대화' 버튼 → chatbot 을 initial_history() 로 초기화
#   chat_page        gr.Column   채팅 화면 전체
#   nav_chat_btn     gr.Button   하단 탭 'Chatbot' (항상 선택 상태)
#   nav_profile_btn  gr.Button   하단 탭 'Profile' → 알림창만 띄움 (PROFILE_ALERT_JS)
# elem_id / elem_classes 는 CSS(app.css)가 사용하므로 이름을 바꾸지 마세요.
# ===========================================================================
with gr.Blocks(title=S["page_title"], fill_height=True, elem_id="app-shell") as demo:
    # ---- Header -----------------------------------------------------------
    with gr.Row(elem_id="app-header", equal_height=True):
        gr.HTML(
            f"""
            <div class="header-title">
              <span>{S["header"]["title"]}</span>
              <span class="online-dot" role="status" aria-label="{S["header"]["status_online"]}"></span>
            </div>
            """,
            elem_id="header-title-wrap",
            padding=False,
        )
        new_chat_btn = gr.Button(
            value="",
            elem_id="new-chat-btn",
            elem_classes=["icon-btn", "fx-ripple"],
            scale=0,
            min_width=24,
        )

    # ---- Chat page --------------------------------------------------------
    with gr.Column(elem_id="chat-page", visible=True) as chat_page:
        chatbot = gr.Chatbot(
            value=initial_history(),
            elem_id="chat",
            show_label=False,
            container=False,
            buttons=["copy"],       # 봇 말풍선 옆 복사 버튼
            layout="bubble",
            avatar_images=None,
            render_markdown=True,   # 봇 답변에 마크다운 사용 가능
            autoscroll=True,
            scale=1,
        )
        with gr.Row(elem_id="composer", equal_height=True):
            msg = gr.Textbox(
                placeholder=S["composer"]["placeholder"],
                show_label=False,
                container=False,
                lines=1,
                max_lines=4,
                autofocus=True,
                elem_id="composer-input",
                scale=1,
            )
            send_btn = gr.Button(
                value="",
                elem_id="send-btn",
                elem_classes=["fx-ripple"],
                scale=0,
                min_width=54,
            )

    # ---- Bottom nav -------------------------------------------------------
    with gr.Row(elem_id="bottom-nav"):
        nav_chat_btn = gr.Button(
            S["nav"]["chatbot"], elem_classes=["nav-btn", "nav-chatbot", "active"], scale=0
        )
        nav_profile_btn = gr.Button(
            S["nav"]["profile"], elem_classes=["nav-btn", "nav-profile"], scale=0
        )

    # ---- Events -----------------------------------------------------------
    # 전송 흐름 (Enter 또는 전송 버튼):
    #   add_user_message → lock(버튼 잠금) → stream_bot(답변 스트리밍) → unlock(버튼 해제)
    # queue=False 단계는 즉시 실행, stream_bot 은 큐에서 실행되어 여러 사용자가 동시에 써도 안전합니다.
    lock = lambda: gr.update(interactive=False, elem_classes=["fx-ripple", "pending"])
    unlock = lambda: gr.update(interactive=True, elem_classes=["fx-ripple"])

    for trigger in (msg.submit, send_btn.click):
        (
            trigger(add_user_message, [msg, chatbot], [msg, chatbot], queue=False)
            .then(lock, None, send_btn, queue=False)
            .then(stream_bot, chatbot, chatbot)
            .then(unlock, None, send_btn, queue=False)
        )

    new_chat_btn.click(initial_history, None, chatbot, queue=False)

    # Profile 탭: 서버 함수 없이(fn=None) 브라우저에서 알림창만 띄웁니다. 화면 전환 없음.
    nav_profile_btn.click(fn=None, inputs=None, outputs=None, js=PROFILE_ALERT_JS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # 첫 질문이 오래 걸리지 않도록 서버 시작 전에 PDF 벡터 DB를 미리 만듭니다.
    get_db()
    # 배포 시 자주 바꾸는 옵션: server_name="0.0.0.0", server_port=7860, root_path="/chat"
    demo.launch(
        css=build_css(),
        js=(ASSETS / "effects.js").read_text(encoding="utf-8"),
        head=build_head(),
        theme=gr.themes.Base(),
        footer_links=[],
    )
