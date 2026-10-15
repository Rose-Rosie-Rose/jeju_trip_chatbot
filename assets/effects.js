() => {
  /* effects.js — CSS만으로 안 되는 인터랙션
     0) 라이트 모드 고정   1) .fx-ripple 버튼 리플   2) 전송 시 종이비행기 애니메이션
     3) 마지막 사용자 말풍선 표시(.is-latest)   4) 아이콘 버튼 접근성 라벨 */
  if (window.__jejuFx) return;
  window.__jejuFx = true;

  // 0) Light mode lock --------------------------------------------------------
  // OS 가 다크 모드면 Gradio 가 <body class="dark"> 를 붙여 글자가 흰색이 됩니다.
  // 이 디자인은 라이트 전용이라 dark 클래스를 지우고, 다시 붙으면 또 지웁니다.
  const forceLight = () => document.body.classList.remove("dark");
  forceLight();
  new MutationObserver(forceLight).observe(document.body, { attributes: true, attributeFilter: ["class"] });

  const S = window.APP_STRINGS || {};
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // 1) Ripple ---------------------------------------------------------------
  document.addEventListener("pointerdown", (e) => {
    const btn = e.target.closest(".fx-ripple, .nav-btn");
    if (!btn || btn.disabled || reduceMotion) return;
    const rect = btn.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    const ink = document.createElement("span");
    ink.className = "fx-ink";
    ink.style.width = ink.style.height = `${size}px`;
    ink.style.left = `${e.clientX - rect.left - size / 2}px`;
    ink.style.top = `${e.clientY - rect.top - size / 2}px`;
    btn.appendChild(ink);
    ink.addEventListener("animationend", () => ink.remove(), { once: true });
  });

  // 2) Paper-plane fly on send ---------------------------------------------
  const fly = () => {
    const btn = document.getElementById("send-btn");
    if (!btn || btn.disabled) return;
    btn.classList.remove("fx-fly");
    void btn.offsetWidth;               // 애니메이션 재시작
    btn.classList.add("fx-fly");
    btn.addEventListener("animationend", () => btn.classList.remove("fx-fly"), { once: true });
  };
  document.addEventListener("click", (e) => {
    if (e.target.closest("#send-btn")) fly();
  }, true);
  document.addEventListener("keydown", (e) => {
    const ta = e.target.closest("#composer-input textarea");
    if (ta && e.key === "Enter" && !e.shiftKey && !e.isComposing && ta.value.trim()) fly();
  }, true);

  // 3) Latest user bubble + 4) a11y labels ----------------------------------
  const sync = () => {
    const rows = document.querySelectorAll("#chat .user-row");
    rows.forEach((r, i) => r.classList.toggle("is-latest", i === rows.length - 1));

    const label = (sel, text) => {
      const el = document.querySelector(sel);
      if (el && text && el.getAttribute("aria-label") !== text) {
        el.setAttribute("aria-label", text);
        el.setAttribute("title", text);
      }
    };
    label("#send-btn", S.composer && S.composer.send);
    label("#new-chat-btn", S.header && S.header.new_chat);
  };
  new MutationObserver(sync).observe(document.body, { childList: true, subtree: true });
  sync();
}
