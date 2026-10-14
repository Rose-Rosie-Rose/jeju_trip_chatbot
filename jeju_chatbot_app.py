"""
Jeju Chatbot - Figma "jeju chatbot - palette (sand)" 화면을 Gradio로 옮긴 버전

실행:
    pip install "gradio>=6"
    python jeju_chatbot_app.py

실제 AI 답변을 붙이려면 아래 generate_reply() 안만 바꾸면 됩니다.
디자인(색상, CSS, 폰트, 말풍선 투명도)은 같은 폴더의 style_css.py에 있습니다.
"""

import gradio as gr

from style_css import CSS, HEAD, FADE_JS, ORANGE, NAV_DARK  # 디자인은 style_css.py에서 관리


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
