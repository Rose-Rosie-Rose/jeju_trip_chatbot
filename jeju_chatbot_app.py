"""
Jeju Chatbot - Figma "jeju chatbot - palette (sand)" 화면을 Gradio로 옮긴 버전

실행:
    pip install "gradio>=6"
    python jeju_chatbot_app.py

실제 AI 답변을 붙이려면 아래 generate_reply() 안만 바꾸면 됩니다.
"""

import gradio as gr

# ── Figma에서 가져온 디자인 토큰 ──────────────────────────────
ORANGE = "#ff993f"      # 내 말풍선, 전송 버튼, 활성 탭, 아이콘
SAND = "#c9a37c"        # 입력창 테두리
GREEN = "#9ed454"       # 온라인 표시 점
LEMON = "#fefc9e"       # 배경 그라데이션 시작
IVORY = "#f8f1e9"       # 배경 그라데이션 중간
TEXT_DARK = "#373435"   # 본문 글자
NAV_DARK = "#201d2f"    # 비활성 탭
PLACEHOLDER = "#9e9e9e"

# 말풍선 배경 불투명도: 대화창 맨 아래는 MAX, 천장(맨 위)으로 갈수록 내려가서 최소 MIN까지
# (Figma 시안: 아래에서 위로 1.0 → 0.9 → 0.8 → 0.7 → 0.6)
BUBBLE_ALPHA_MIN = 0.5
BUBBLE_ALPHA_MAX = 1.0


def generate_reply(message: str, history: list) -> str:
    """챗봇 답변 생성. 여기를 OpenAI / Claude / 사내 LLM 호출로 바꾸세요."""
    text = message.strip()
    if "이름" in text or "name" in text.lower():
        return ('How about the name **"VentureQuest"**? It combines the sense of adventure '
                "with a quest for exploration. Let me know if you'd like more suggestions!")
    return f"'{text}'에 대해 알려드릴게요. (데모 응답입니다. generate_reply()에 실제 모델을 연결하세요.)"


# 시안에 있던 대화를 첫 화면 예시로 넣어 둡니다.
INITIAL_HISTORY = [
    {"role": "user", "content": "Hello ! there"},
    {"role": "assistant", "content": "Hello there! How may I assist you today?"},
    {"role": "user", "content": "I'm looking for a name that reflects adventure and exploration."},
    {"role": "assistant", "content": ('How about the name **"VentureQuest"**? It combines the sense of adventure '
                                      "with a quest for exploration. Let me know if you'd like more suggestions "
                                      "or if there's anything specific you have in mind!")},
]


def respond(message, history):
    if not message or not message.strip():
        return "", history
    history = history + [{"role": "user", "content": message}]
    history = history + [{"role": "assistant", "content": generate_reply(message, history)}]
    return "", history


# ── 아이콘 (inline SVG) ─────────────────────────────────────
def icon(path, color, size=24, fill="none"):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="{fill}" stroke="{color}" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{path}</svg>')

CHAT_ICON = icon('<path d="M12 3C7 3 3 6.6 3 11c0 2.3 1.1 4.4 2.9 5.9L5 21l4.3-2.1c.9.2 1.8.3 2.7.3 5 0 9-3.6 9-8.1S17 3 12 3z"/>'
                 '<circle cx="8" cy="11" r=".6" fill="#201d2f"/><circle cx="12" cy="11" r=".6" fill="#201d2f"/><circle cx="16" cy="11" r=".6" fill="#201d2f"/>', NAV_DARK)
HOME_ICON = icon('<path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-4v-6h-6v6H5a1 1 0 0 1-1-1z"/>', NAV_DARK)
SAVED_ICON = icon('<path d="M6 3h12v18l-6-4-6 4z"/>', NAV_DARK)
BOT_ICON = icon('<rect x="4" y="8" width="16" height="12" rx="3" fill="#ff993f" stroke="#ff993f"/>'
                '<path d="M12 4v4"/><circle cx="12" cy="3.5" r="1.2" fill="#ff993f"/>'
                '<circle cx="9" cy="14" r="1.3" fill="#fff" stroke="none"/><circle cx="15" cy="14" r="1.3" fill="#fff" stroke="none"/>'
                '<path d="M2 13v3M22 13v3"/>', ORANGE)
PROFILE_ICON = icon('<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5"/>', NAV_DARK)

HEADER_HTML = f"""
<div class="jj-header">
  <div class="jj-title">Chatbot AI <span class="jj-dot"></span></div>
  <div class="jj-header-icon">{CHAT_ICON}</div>
</div>
"""

NAV_HTML = f"""
<nav class="jj-nav">
  <div class="jj-tab">{HOME_ICON}<span>Home</span></div>
  <div class="jj-tab">{SAVED_ICON}<span>Saved</span></div>
  <div class="jj-tab active">{BOT_ICON}<span>Chatbot</span></div>
  <div class="jj-tab">{PROFILE_ICON}<span>Profile</span></div>
</nav>
"""

HEAD = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;700&display=swap" rel="stylesheet">')

CSS = f"""
/* 페이지 전체 */
body, .gradio-container {{
  font-family: 'Plus Jakarta Sans', 'Pretendard', sans-serif !important;
  background: #ece6dd !important;
}}
.gradio-container, .gradio-container .main, .gradio-container .wrap, .gradio-container .contain, .gradio-container .fillable {{
  max-width: 100% !important; padding: 0 !important; }}
footer {{ display: none !important; }}

/* 휴대폰 프레임 (428 x 926) */
#jj-phone {{
  max-width: 428px; height: min(926px, 100vh); margin: 0 auto;
  background: linear-gradient(180deg, {LEMON} 0%, {IVORY} 55%, #ffffff 100%);
  display: flex; flex-direction: column; gap: 0 !important;
  overflow: hidden; border-radius: 0; box-shadow: 0 10px 40px rgba(24,39,75,.12);
}}
@media (min-width: 500px) {{ #jj-phone {{ margin: 24px auto; border-radius: 36px; height: min(926px, calc(100vh - 48px)); }} }}
#jj-phone > * {{ flex-shrink: 0; }}

/* 헤더 */
.jj-header {{ position: relative; height: 62px; display: flex; align-items: center; justify-content: center;
  border-bottom: 1px solid {ORANGE}; margin-top: 8px; }}
.jj-title {{ font-size: 20px; font-weight: 500; color: {TEXT_DARK}; display: flex; align-items: center; gap: 6px; }}
.jj-dot {{ width: 8px; height: 8px; border-radius: 50%; background: {GREEN}; display: inline-block; }}
.jj-header-icon {{ position: absolute; right: 24px; top: 50%; transform: translateY(-50%); display: flex; }}

/* 대화 영역 */
#jj-chat {{ flex: 1 1 auto !important; min-height: 0; background: transparent !important; border: none !important; box-shadow: none !important; }}
#jj-chat > div, #jj-chat .wrapper, #jj-chat .bubble-wrap {{ background: transparent !important; }}
#jj-chat .bubble-wrap {{ padding: 20px 24px !important; }}
#jj-chat .message-wrap {{ gap: 0 !important; }}
#jj-chat .message-row {{ margin: 0 0 8px 0 !important; padding: 0 !important; }}
/* 바깥 말풍선만 스타일링하고, 안쪽 .message는 투명하게 */
#jj-chat .role > .message {{
  font-size: 16px !important; line-height: 21px !important; padding: 15px 16px !important;
  max-width: 308px !important; box-shadow: none !important; width: fit-content !important;
}}
#jj-chat .message .message {{ background: transparent !important; border: none !important; padding: 0 !important;
  box-shadow: none !important; max-width: none !important; }}
#jj-chat .message-content, #jj-chat .prose, #jj-chat .prose * {{ font-size: 16px !important; line-height: 21px !important; margin: 0 !important; }}
/* --jj-a: 화면 속 위치에 따라 JS가 0.5~1.0으로 갱신 (글자는 그대로, 배경만 옅어짐) */
#jj-chat .role > .message.user {{
  background: rgba(255,153,63,var(--jj-a, 1)) !important; border: none !important;
  transition: background-color .25s ease;
  border-radius: 19px 19px 0 19px !important; max-width: 255px !important; padding: 15px !important;
}}
#jj-chat .role > .message.user * {{ color: #fff !important; }}
#jj-chat .role > .message.bot {{
  background: rgba(255,255,255,var(--jj-a, 1)) !important; border: 1px solid rgba(255,153,63,.45) !important;
  transition: background-color .25s ease;
  border-radius: 19px 19px 19px 0 !important;
}}
#jj-chat .role > .message.bot * {{ color: {TEXT_DARK} !important; }}
#jj-chat .message.bot strong {{ font-weight: 700; }}
#jj-chat .message-buttons-left, #jj-chat .message-buttons-right, #jj-chat .message-buttons {{ border: none !important; background: transparent !important; }}
#jj-chat .message-buttons button, #jj-chat .message-row button {{ color: {ORANGE} !important; background: transparent !important; border: none !important; box-shadow: none !important; }}
#jj-chat .top-panel, #jj-chat > .icon-button-wrapper {{ display: none !important; }}

/* 입력 영역 */
#jj-input-row {{ padding: 16px 24px 20px !important; gap: 20px !important; align-items: center !important;
  background: transparent !important; border: none !important; flex-wrap: nowrap !important; }}
#jj-input {{ flex: 1 1 auto !important; min-width: 0 !important; background: transparent !important; border: none !important; padding: 0 !important; }}
#jj-input input {{
  height: 54px !important; min-height: 54px !important; padding: 15px 48px 15px 16px !important;
  font-size: 16px !important; font-weight: 500; color: {TEXT_DARK} !important;
  background: #fff url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%23ff993f' stroke-width='1.8' stroke-linecap='round'><rect x='9' y='3' width='6' height='11' rx='3'/><path d='M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M9 21h6'/></svg>") no-repeat right 16px center !important;
  border: 1px solid rgba(201,163,124,.6) !important; border-radius: 12px !important;
  box-shadow: 0 14px 64px rgba(24,39,75,.12), 0 8px 22px rgba(24,39,75,.12) !important; resize: none !important;
}}
#jj-input input::placeholder {{ color: {PLACEHOLDER}; }}
#jj-send {{
  width: 54px !important; min-width: 54px !important; max-width: 54px !important; height: 54px !important;
  border-radius: 50% !important; background: {ORANGE} !important; border: none !important; padding: 0 !important;
  flex: 0 0 54px !important;
}}
#jj-send:hover {{ filter: brightness(1.05); }}
#jj-send {{ background: {ORANGE} url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='26' height='26' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='1.8' stroke-linejoin='round'><path d='M3 4l18 8-18 8 3-8z'/><path d='M6 12h7'/></svg>") no-repeat center !important; }}

/* 하단 탭 */
#jj-nav-wrap {{ padding: 0 !important; }}
.jj-nav {{ height: 72px; background: #fff; display: flex; justify-content: space-around; align-items: center; padding: 0 20px; }}
.jj-tab {{ display: flex; flex-direction: column; align-items: center; gap: 4px; font-size: 10px; font-weight: 500;
  color: {NAV_DARK}; cursor: pointer; width: 64px; }}
.jj-tab span {{ color: {NAV_DARK} !important; font-size: 10px !important; }}
.jj-tab.active span {{ color: {ORANGE} !important; }}
#jj-header-wrap, #jj-nav-wrap, #jj-header-wrap .html-container, #jj-nav-wrap .html-container, #jj-header-wrap .prose, #jj-nav-wrap .prose {{
  padding: 0 !important; margin: 0 !important; max-width: none !important; border: none !important; background: transparent !important; }}
.jj-header {{ border-bottom: 1px solid {ORANGE} !important; }}
"""

# 말풍선이 대화창 위쪽(천장)에 가까울수록 배경을 투명하게 만드는 스크립트.
# 스크롤, 창 크기 변경, 새 메시지가 생길 때마다 다시 계산합니다.
FADE_JS = f"""
() => {{
  const MIN = {BUBBLE_ALPHA_MIN}, MAX = {BUBBLE_ALPHA_MAX};
  const isScroller = el => el && /(auto|scroll)/.test(getComputedStyle(el).overflowY) && el.scrollHeight > el.clientHeight;
  function update() {{
    const chat = document.querySelector('#jj-chat');
    if (!chat) return;
    const bubbles = chat.querySelectorAll('.role > .message');
    if (!bubbles.length) return;
    let box = bubbles[0].parentElement;
    while (box && box !== chat.parentElement && !isScroller(box)) box = box.parentElement;
    const r = (box && isScroller(box) ? box : chat).getBoundingClientRect();
    bubbles.forEach(b => {{
      const br = b.getBoundingClientRect();
      const t = Math.min(1, Math.max(0, (br.top + br.height / 2 - r.top) / r.height));  // 0=천장, 1=바닥
      b.style.setProperty('--jj-a', (MIN + (MAX - MIN) * t).toFixed(3));
    }});
  }}
  let queued = false;
  const schedule = () => {{ if (!queued) {{ queued = true; requestAnimationFrame(() => {{ queued = false; update(); }}); }} }};
  document.addEventListener('scroll', schedule, true);
  window.addEventListener('resize', schedule);
  new MutationObserver(schedule).observe(document.body, {{ childList: true, subtree: true }});
  schedule();
}}
"""


with gr.Blocks(title="Jeju Chatbot", fill_width=True) as demo:
    with gr.Column(elem_id="jj-phone"):
        gr.HTML(HEADER_HTML, elem_id="jj-header-wrap", padding=False)
        chat = gr.Chatbot(
            value=INITIAL_HISTORY,
            elem_id="jj-chat",
            show_label=False,
            buttons=["copy"],
            layout="bubble",
            container=False,
        )
        with gr.Row(elem_id="jj-input-row", equal_height=True):
            msg = gr.Textbox(
                placeholder="Generate a name of ....",
                show_label=False,
                container=False,
                lines=1,
                max_lines=1,
                elem_id="jj-input",
            )
            send = gr.Button("", elem_id="jj-send")
        gr.HTML(NAV_HTML, elem_id="jj-nav-wrap", padding=False)

    msg.submit(respond, [msg, chat], [msg, chat])
    send.click(respond, [msg, chat], [msg, chat])


if __name__ == "__main__":
    demo.launch(css=CSS, head=HEAD, js=FADE_JS)
