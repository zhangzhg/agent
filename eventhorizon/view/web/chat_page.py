"""view/web/chat_page.py — 单页聊天界面（GAME_DESIGN §2.1 布局的 Web 版）。

纯前端：一个自包含的 HTML/CSS/JS 字符串，靠 fetch() 打 controller/web_controller.py
的 /api/session、/api/chat。没有任何构建步骤，也不依赖外部 CDN——单机本地小工具，
没必要引入前端框架。
"""
from __future__ import annotations

PAGE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>太一仙途</title>
<style>
  :root {
    --bg: #1c1a17;
    --panel-bg: #262320;
    --border: #3a352e;
    --text: #e8e0d0;
    --text-dim: #9a9182;
    --accent: #c9a35c;
    --narrative-bg: transparent;
    --system-bg: #322d27;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    display: flex;
    flex-direction: column;
    background: var(--bg);
    color: var(--text);
    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
    font-size: 15px;
  }
  header {
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    font-weight: bold;
    letter-spacing: 2px;
    color: var(--accent);
  }
  #layout {
    flex: 1;
    display: flex;
    min-height: 0;
  }
  #main {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    border-right: 1px solid var(--border);
  }
  #log {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    line-height: 1.7;
  }
  .bubble { margin-bottom: 14px; white-space: pre-wrap; }
  .bubble.narrative { background: var(--narrative-bg); }
  .bubble.system {
    background: var(--system-bg);
    color: var(--text-dim);
    font-style: italic;
    padding: 6px 10px;
    border-radius: 6px;
    display: inline-block;
  }
  .bubble.user {
    color: var(--accent);
    text-align: right;
  }
  .diff-line { color: var(--text-dim); font-size: 13px; margin: 2px 0 0 4px; }
  #input-bar {
    display: flex;
    border-top: 1px solid var(--border);
    padding: 10px;
    gap: 8px;
  }
  #input-bar input {
    flex: 1;
    background: var(--panel-bg);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 10px 12px;
    border-radius: 6px;
    font-size: 15px;
  }
  #input-bar input:focus { outline: 1px solid var(--accent); }
  #input-bar button {
    background: var(--accent);
    color: #1c1a17;
    border: none;
    padding: 0 18px;
    border-radius: 6px;
    font-weight: bold;
    cursor: pointer;
  }
  #sidebar {
    width: 260px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    background: var(--panel-bg);
  }
  .panel {
    padding: 12px 14px;
    border-bottom: 1px solid var(--border);
  }
  .panel .row { display: flex; justify-content: space-between; margin: 4px 0; }
  .panel .label { color: var(--text-dim); }
  .tidal { color: var(--accent); }
  @media (max-width: 640px) {
    #layout { flex-direction: column; }
    #sidebar { width: 100%; flex-direction: row; flex-wrap: wrap; }
    .panel { flex: 1 1 45%; }
  }
</style>
</head>
<body>
  <header>太一仙途</header>
  <div id="layout">
    <div id="main">
      <div id="log"></div>
      <div id="input-bar">
        <input id="text-input" type="text" placeholder="输入你想做什么…" autocomplete="off" />
        <button id="send-btn">发送</button>
      </div>
    </div>
    <div id="sidebar">
      <div class="panel" id="panel-calendar"></div>
      <div class="panel" id="panel-location"></div>
      <div class="panel" id="panel-character"></div>
    </div>
  </div>

<script>
const AGENT_ID = new URLSearchParams(location.search).get("agent") || "player";

const log = document.getElementById("log");
const input = document.getElementById("text-input");
const sendBtn = document.getElementById("send-btn");

function appendBubble(text, cls) {
  const div = document.createElement("div");
  div.className = "bubble " + cls;
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

function appendDiffLines(lines) {
  for (const line of lines || []) {
    const div = document.createElement("div");
    div.className = "diff-line";
    div.textContent = "· " + line;
    log.appendChild(div);
  }
  log.scrollTop = log.scrollHeight;
}

function updateSidebar(sidebar) {
  if (!sidebar) return;
  const cal = sidebar.calendar;
  document.getElementById("panel-calendar").innerHTML =
    `<div>${cal.text}</div>` + (cal.is_tidal_day ? `<div class="tidal">☾ 灵气潮汐</div>` : "");

  const loc = sidebar.location;
  document.getElementById("panel-location").innerHTML =
    `<div class="row"><span>${loc.name}</span><span class="label">${loc.location_type}</span></div>` +
    `<div class="row"><span class="label">灵气</span><span>${loc.qi_density_icons}</span></div>` +
    `<div class="row"><span class="label">天气</span><span>${loc.weather}</span></div>`;

  const ch = sidebar.character;
  document.getElementById("panel-character").innerHTML =
    `<div class="row"><span>${ch.cultivation_progress_text}</span></div>` +
    `<div class="row"><span class="label">寿元</span><span>${ch.lifespan_label}</span></div>` +
    `<div class="row"><span class="label">饱食</span><span>${ch.satiety_icons}</span></div>` +
    `<div class="row"><span class="label">金钱</span><span>${ch.money}</span></div>` +
    `<div class="row"><span class="label">背包</span><span>${ch.inventory_count}</span></div>`;
}

async function loadSession() {
  const res = await fetch(`/api/session?agent_id=${encodeURIComponent(AGENT_ID)}`);
  const data = await res.json();
  if (data.narrative) appendBubble(data.narrative, "narrative");
  updateSidebar(data.sidebar);
}

async function sendMessage() {
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  appendBubble(text, "user");
  sendBtn.disabled = true;
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_id: AGENT_ID, text }),
    });
    const data = await res.json();
    const isSystem = Boolean(data.parse_error || data.reject_reason);
    appendBubble(data.narrative, isSystem ? "system" : "narrative");
    appendDiffLines(data.state_diff_lines);
    updateSidebar(data.sidebar);
  } catch (err) {
    appendBubble("（网络错误，请重试）", "system");
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
}

sendBtn.addEventListener("click", sendMessage);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendMessage();
});

loadSession();
</script>
</body>
</html>
"""


def render_page() -> str:
    return PAGE_HTML
