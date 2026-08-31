"""view/web/admin_page.py — 录入编辑器页面（ARCHITECTURE §1.3.3 / GAME_DESIGN
§9.3）。

跟 chat_page.py 一样：自包含 HTML/CSS/JS，没有构建步骤、没有外部 CDN。左侧是
分组菜单（地图管理/内容管理/工具），点菜单项切换右侧内容面板——比顶部标签页更
接近常见后台管理系统的样子，条目多了也不会挤成一排。地图/物品走结构化表单；
事件的谓词/结果池/变体/局部选项用 JSON 文本框——那几块是递归的判别联合类型
（AND/OR 谓词树、七种结果类型…），做一个完整的可视化构建器是独立的大工程，这里
先给"看得懂、能校验、能保存"的版本，JSON 判别字段跟
model/services/event_validation.py 校验用的是同一套。
"""
from __future__ import annotations

PAGE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>太一仙途 · 录入编辑器</title>
<style>
  :root {
    --bg: #16181c; --panel-bg: #1e2126; --sidebar-bg: #1a1c20; --border: #33383f;
    --text: #dfe3e8; --text-dim: #8a9099; --accent: #5fa8d3;
    --ok: #6fbf73; --bad: #d9695f; --draft: #c9a35c;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    display: flex;
    background: var(--bg); color: var(--text);
    font-family: "Consolas", "Microsoft YaHei", monospace, sans-serif;
    font-size: 14px;
  }

  /* ---------- 左侧菜单 ---------- */
  #sidebar {
    width: 200px; flex-shrink: 0; background: var(--sidebar-bg);
    border-right: 1px solid var(--border); height: 100vh; overflow-y: auto;
  }
  #sidebar .brand {
    padding: 16px 16px 12px; border-bottom: 1px solid var(--border);
    color: var(--accent); font-weight: bold; font-size: 15px;
  }
  #sidebar .brand small { display: block; color: var(--text-dim); font-weight: normal; font-size: 11px; margin-top: 2px; }
  .menu-group { padding: 10px 0; border-bottom: 1px solid var(--border); }
  .menu-group-title {
    padding: 4px 16px; color: var(--text-dim); font-size: 11px;
    letter-spacing: 1px; text-transform: uppercase;
  }
  .menu-item {
    display: block; width: 100%; text-align: left; background: none; border: none;
    color: var(--text); padding: 8px 16px 8px 24px; cursor: pointer; font-size: 13px;
    border-left: 2px solid transparent;
  }
  .menu-item:hover { background: #22262c; }
  .menu-item.active { background: #22262c; border-left-color: var(--accent); color: var(--accent); }

  /* ---------- 右侧内容 ---------- */
  #content { flex: 1; min-width: 0; height: 100vh; overflow-y: auto; padding: 18px 24px; }
  .pane { display: none; }
  .pane.active { display: block; }
  .pane > h2 { margin: 0 0 14px; font-size: 16px; color: var(--accent); font-weight: normal; }
  .cols { display: flex; gap: 16px; align-items: flex-start; }
  .col { flex: 1; min-width: 0; }

  table { width: 100%; border-collapse: collapse; margin-bottom: 12px; }
  th, td { text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--border); font-size: 13px; }
  th { color: var(--text-dim); font-weight: normal; }
  tr:hover td { background: #22262c; cursor: pointer; }
  tr.row-selected td { background: rgba(95, 168, 211, 0.18); border-left: 2px solid var(--accent); }
  .badge { padding: 1px 6px; border-radius: 3px; font-size: 11px; }
  .badge.draft { background: var(--draft); color: #16181c; }
  .badge.published { background: var(--ok); color: #16181c; }

  fieldset { border: 1px solid var(--border); border-radius: 6px; margin-bottom: 12px; }
  legend { color: var(--accent); padding: 0 6px; }
  label { display: block; margin: 8px 0 3px; color: var(--text-dim); font-size: 12px; }
  input[type=text], input[type=number], select, textarea {
    width: 100%; background: var(--panel-bg); border: 1px solid var(--border);
    color: var(--text); padding: 6px 8px; border-radius: 4px; font-family: inherit; font-size: 13px;
  }
  textarea { min-height: 70px; resize: vertical; white-space: pre; }
  .row2 { display: flex; gap: 10px; }
  .row2 > div { flex: 1; }
  .checkbox-line { display: flex; align-items: center; gap: 6px; margin: 8px 0; }
  .checkbox-line input { width: auto; }
  .btn {
    background: var(--accent); color: #16181c; border: none; padding: 7px 16px;
    border-radius: 4px; cursor: pointer; font-weight: bold; margin-right: 6px; margin-top: 8px;
  }
  .btn.secondary { background: var(--panel-bg); color: var(--text); border: 1px solid var(--border); }
  .btn.danger { background: var(--bad); color: #16181c; }
  .errors { color: var(--bad); font-size: 12px; margin-top: 8px; white-space: pre-wrap; }
  .ok-msg { color: var(--ok); font-size: 12px; margin-top: 8px; }
  .hint { color: var(--text-dim); font-size: 11px; margin-top: 2px; }
  #event-search { margin-bottom: 8px; }
  pre.result { background: var(--panel-bg); border: 1px solid var(--border); padding: 8px; border-radius: 4px; overflow-x: auto; }

  /* ---------- 地图编辑器 ---------- */
  #map-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
  #map-breadcrumb { font-size: 13px; color: var(--text-dim); }
  #map-breadcrumb button {
    background: none; border: none; color: var(--accent); cursor: pointer; padding: 0 3px; font-size: 13px;
    font-family: inherit; text-decoration: underline;
  }
  #map-breadcrumb button:last-child, #map-breadcrumb span.current { color: var(--text); text-decoration: none; cursor: default; }
  #map-canvas-wrap { border: 1px solid var(--border); border-radius: 6px; background: var(--panel-bg); }
  #map-canvas { width: 100%; height: 480px; display: block; cursor: crosshair; }
  #map-canvas .node-circle { fill: var(--accent); stroke: #16181c; stroke-width: 1.5; cursor: grab; }
  #map-canvas .node-circle.hidden-loc { fill: var(--sidebar-bg); stroke: var(--draft); stroke-dasharray: 3 2; }
  #map-canvas .node-circle.selected { stroke: #fff; stroke-width: 2.5; }
  #map-canvas .node-circle.connect-first { stroke: var(--ok); stroke-width: 2.5; }
  #map-canvas .node-label { fill: var(--text); font-size: 11px; font-family: inherit; pointer-events: none; }
  #map-canvas .route-line { stroke: var(--text-dim); stroke-width: 1.5; }
  #map-canvas .route-line.one-way { stroke-dasharray: 4 3; }
  #map-canvas .node-delete-btn { cursor: pointer; }
  #map-canvas .node-delete-btn circle { fill: var(--bad); stroke: #16181c; stroke-width: 1; }
  #map-canvas .node-delete-btn text { fill: #16181c; font-size: 12px; font-weight: bold; pointer-events: none; }
  #map-hint { font-size: 11px; color: var(--text-dim); margin: 6px 0 10px; }
  .btn.toggled { background: var(--ok); }
  .list-header { display: flex; justify-content: space-between; align-items: center; margin: 4px 0 6px; }
  .list-header h3 { margin: 0; font-size: 13px; color: var(--text-dim); font-weight: normal; }

  /* ---------- 弹窗：新增/编辑地点、新增/编辑路线，独立于画布之外 ---------- */
  .modal-overlay {
    display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.55);
    align-items: center; justify-content: center; z-index: 100;
  }
  .modal-overlay.open { display: flex; }
  .modal-box {
    background: var(--panel-bg); border: 1px solid var(--border); border-radius: 8px;
    width: 420px; max-width: 92vw; max-height: 88vh; overflow-y: auto; padding: 16px 18px;
  }
  .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
  .modal-header span { color: var(--accent); font-size: 15px; }
  .modal-close { background: none; border: none; color: var(--text-dim); font-size: 20px; cursor: pointer; line-height: 1; }
  .modal-footer { display: flex; gap: 6px; margin-top: 10px; flex-wrap: wrap; }
  @media (max-width: 720px) {
    body { flex-direction: column; }
    #sidebar { width: 100%; height: auto; }
    #content { height: auto; }
  }
</style>
</head>
<body>

<aside id="sidebar">
  <div class="brand">太一仙途<small>录入编辑器</small></div>
  <div class="menu-group">
    <div class="menu-group-title">地图管理</div>
    <button class="menu-item active" data-pane="mapeditor">地图编辑器</button>
  </div>
  <div class="menu-group">
    <div class="menu-group-title">内容管理</div>
    <button class="menu-item" data-pane="items">物品</button>
    <button class="menu-item" data-pane="events">事件</button>
  </div>
  <div class="menu-group">
    <div class="menu-group-title">工具</div>
    <button class="menu-item" data-pane="simulate">模拟触发</button>
  </div>
</aside>

<div id="content">

<!-- ===================== 地图编辑器 ===================== -->
<div class="pane active" id="pane-mapeditor">
  <h2>地图编辑器</h2>
  <div id="map-toolbar">
    <span id="map-breadcrumb"></span>
    <button class="btn secondary" id="map-connect-btn" onclick="toggleConnectMode()">连接路线</button>
    <button class="btn secondary" onclick="openLocationModal(null)">+ 新建地点</button>
  </div>
  <div id="map-hint">
    点节点只选中、在右侧列表高亮，不弹窗；双击节点下钻进入其内部子图；拖拽节点调整位置；
    点空白处取消选中。要新增/编辑，去右侧列表点行或"编辑"按钮；"连接路线"模式下依次点
    两个节点，弹出新增路线的表单确认。
  </div>
  <div class="cols">
    <div class="col" style="flex: 2;">
      <div id="map-canvas-wrap">
        <svg id="map-canvas" viewBox="0 0 900 480"></svg>
      </div>
    </div>
    <div class="col">
      <div class="list-header"><h3>地点列表（当前层级）</h3><button class="btn secondary" onclick="openLocationModal(null)">+ 新建</button></div>
      <table id="location-table"><thead>
        <tr><th>ID</th><th>名称</th><th>类型</th><th></th></tr>
      </thead><tbody></tbody></table>

      <div class="list-header"><h3>路线列表（当前层级）</h3><button class="btn secondary" onclick="openRouteModal(null)">+ 新建</button></div>
      <table id="route-table"><thead>
        <tr><th>起点</th><th>终点</th><th>耗时</th><th>双向</th><th></th></tr>
      </thead><tbody></tbody></table>
    </div>
  </div>

  <!-- 新增/编辑地点：独立弹窗，不占画布/列表的地方 -->
  <div class="modal-overlay" id="location-modal-overlay">
    <div class="modal-box">
      <div class="modal-header">
        <span id="location-modal-title">新增地点</span>
        <button class="modal-close" onclick="closeLocationModal()">×</button>
      </div>
      <label>location_id</label><input type="text" id="loc-id" />
      <label>名称</label><input type="text" id="loc-name" />
      <div class="row2">
        <div><label>kind</label>
          <select id="loc-kind">
            <option value="城市">城市</option><option value="荒野">荒野</option>
            <option value="洞府">洞府</option><option value="集市">集市</option>
            <option value="山门">山门</option><option value="遗迹">遗迹</option>
            <option value="秘境">秘境</option>
          </select>
        </div>
        <div><label>location_type（粗筛匹配键）</label><input type="text" id="loc-type" /></div>
      </div>
      <div class="row2">
        <div><label>灵气浓度</label><input type="number" step="0.1" id="loc-qi" value="1.0" /></div>
        <div><label>危险等级</label><input type="number" step="0.1" id="loc-danger" value="0" /></div>
      </div>
      <div class="row2">
        <div><label>condition</label>
          <select id="loc-condition">
            <option value="完好">完好</option><option value="废墟">废墟</option><option value="秘境开启">秘境开启</option>
          </select>
        </div>
        <div><label>父地点（点画布空白处新建时自动填入）</label><input type="text" id="loc-parent" readonly /></div>
      </div>
      <div class="row2">
        <div><label>x 坐标</label><input type="number" id="loc-x" value="0" /></div>
        <div><label>y 坐标</label><input type="number" id="loc-y" value="0" /></div>
      </div>
      <div class="checkbox-line"><input type="checkbox" id="loc-hidden" /><label style="margin:0">隐藏点位（需神识扫描发现）</label></div>
      <div class="row2">
        <div><label>隐蔽度（0~1）</label><input type="number" step="0.05" id="loc-concealment" value="0" /></div>
        <div class="checkbox-line" style="margin-top:22px"><input type="checkbox" id="loc-discovered" /><label style="margin:0">已发现</label></div>
      </div>
      <div class="errors" id="loc-errors"></div>
      <div class="modal-footer">
        <button class="btn" onclick="saveLocation()">保存</button>
        <button class="btn secondary" onclick="closeLocationModal()">取消</button>
        <button class="btn danger" id="loc-delete-btn" onclick="deleteLocation(mapSelectedId || $('loc-id').value)" style="display:none">删除此地点</button>
      </div>
    </div>
  </div>

  <!-- 新增/编辑路线：独立弹窗 -->
  <div class="modal-overlay" id="route-modal-overlay">
    <div class="modal-box">
      <div class="modal-header">
        <span id="route-modal-title">新增路线</span>
        <button class="modal-close" onclick="closeRouteModal()">×</button>
      </div>
      <div class="row2">
        <div><label>起点 id</label><input type="text" id="route-from" /></div>
        <div><label>终点 id</label><input type="text" id="route-to" /></div>
      </div>
      <div class="row2">
        <div><label>耗时（时辰）</label><input type="number" id="route-cost" value="1" /></div>
        <div class="checkbox-line" style="margin-top:22px"><input type="checkbox" id="route-bidir" checked /><label style="margin:0">双向</label></div>
      </div>
      <div class="errors" id="route-errors"></div>
      <div class="modal-footer">
        <button class="btn" onclick="saveRoute()">保存</button>
        <button class="btn secondary" onclick="closeRouteModal()">取消</button>
      </div>
    </div>
  </div>
</div>

<!-- ===================== 物品 ===================== -->
<div class="pane" id="pane-items">
  <h2>物品</h2>
  <div class="cols">
    <div class="col">
      <table id="item-table"><thead>
        <tr><th>ID</th><th>名称</th><th>类型</th><th>描述</th><th></th></tr>
      </thead><tbody></tbody></table>
    </div>
    <div class="col">
      <fieldset>
        <legend>新增 / 编辑物品</legend>
        <label>item_id</label><input type="text" id="item-id" />
        <label>名称</label><input type="text" id="item-name" />
        <label>kind</label>
        <select id="item-kind">
          <option value="food">food 食物</option><option value="pill">pill 丹药</option>
          <option value="manual">manual 秘籍</option><option value="material">material 材料</option>
          <option value="gear">gear 装备</option>
        </select>
        <label>描述</label><textarea id="item-desc"></textarea>
        <div class="checkbox-line"><input type="checkbox" id="item-stackable" checked /><label style="margin:0">可堆叠</label></div>
        <div class="checkbox-line"><input type="checkbox" id="item-unique" /><label style="margin:0">唯一</label></div>
        <button class="btn" onclick="saveItem()">保存物品</button>
        <button class="btn secondary" onclick="clearItemForm()">清空</button>
        <div class="errors" id="item-errors"></div>
      </fieldset>
    </div>
  </div>
</div>

<!-- ===================== 事件 ===================== -->
<div class="pane" id="pane-events">
  <h2>事件</h2>
  <div class="cols">
    <div class="col" style="flex: 0 0 260px;">
      <input type="text" id="event-search" placeholder="搜索 event_id / 标签…" oninput="renderEventList()" />
      <table><tbody id="event-list"></tbody></table>
      <button class="btn secondary" onclick="clearEventForm()">+ 新建事件</button>
    </div>
    <div class="col">
      <fieldset>
        <legend>基础信息</legend>
        <div class="row2">
          <div><label>event_id</label><input type="text" id="ev-id" /></div>
          <div><label>优先级 priority</label><input type="number" id="ev-priority" value="5" /></div>
        </div>
        <label>适用地点类型（逗号分隔，"*" 表示任意）</label><input type="text" id="ev-locations" value="*" />
        <label>适用时辰（逗号分隔的 0-11，留空=任意）</label><input type="text" id="ev-time" />
        <div class="row2">
          <div><label>权重 weight</label><input type="number" step="0.1" id="ev-weight" value="1.0" /></div>
          <div><label>持续时辰 duration_shichen</label><input type="number" id="ev-duration" value="1" /></div>
        </div>
        <div class="row2">
          <div><label>冷却时辰 cooldown_shichen</label><input type="number" id="ev-cooldown" value="0" /></div>
          <div><label>最大触发次数（留空=不限）</label><input type="number" id="ev-max-trigger" /></div>
        </div>
        <label>标签 tags（逗号分隔，如 生活,奇遇）</label><input type="text" id="ev-tags" />
        <label>互斥标签 exclusive_tags（逗号分隔）</label><input type="text" id="ev-exclusive" />
        <label>聊天别名 aliases（逗号分隔，命令型事件用）</label><input type="text" id="ev-aliases" />
        <label>scenario_ref（可选，绑定的流程图 id）</label><input type="text" id="ev-scenario-ref" />
        <div class="checkbox-line"><input type="checkbox" id="ev-is-command" /><label style="margin:0">命令型事件（is_command）</label></div>
        <div class="checkbox-line"><input type="checkbox" id="ev-is-draft" checked /><label style="margin:0">草稿（不进合格池）</label></div>
      </fieldset>

      <fieldset>
        <legend>谓词 predicate（JSON，留空 = 无条件）</legend>
        <textarea id="ev-predicate" placeholder='{"op":"AND","items":[{"type":"money_gte","args":[5]}]}'></textarea>
        <div class="hint">白名单类型：attr_gte / attr_eq / realm_gte / money_gte / age_gte / has_item / flag / location_type / has_cause</div>
      </fieldset>

      <fieldset>
        <legend>结果池 result_pool（JSON 数组）</legend>
        <textarea id="ev-results" placeholder='[{"kind":"state_change","field":"money","delta":-2}]'></textarea>
        <div class="hint">kind：item_drop / item_consume / state_change / check / write_cause / chain_event / start_scenario / flag_set / flag_clear</div>
      </fieldset>

      <fieldset>
        <legend>文案变体 variants（JSON 数组，至少 1 条）</legend>
        <textarea id="ev-variants" placeholder='[{"text":"你吃了饭。","weight":1.0}]'></textarea>
        <div class="hint">占位符白名单：{地点} {境界} {金钱} {年龄} {天气} {对象}</div>
      </fieldset>

      <fieldset>
        <legend>局部选项 reply_options（JSON 数组，needs_reply 事件用）</legend>
        <textarea id="ev-reply-options" placeholder='[{"aliases":["买下来"],"results":[],"response_text":"你付了钱。"}]'></textarea>
      </fieldset>

      <button class="btn" onclick="saveEvent()">保存草稿</button>
      <button class="btn" onclick="publishEvent()">发布</button>
      <button class="btn secondary" onclick="unpublishEvent()">撤回为草稿</button>
      <button class="btn danger" onclick="deleteEvent()">删除</button>
      <div class="errors" id="ev-errors"></div>
      <div class="ok-msg" id="ev-ok"></div>
    </div>
  </div>
</div>

<!-- ===================== 模拟触发 ===================== -->
<div class="pane" id="pane-simulate">
  <h2>模拟触发沙盒</h2>
  <div class="cols">
    <div class="col">
      <fieldset>
        <legend>测试参数</legend>
        <label>event_id</label><input type="text" id="sim-event-id" placeholder="要测试的事件 id" />
        <label>测试快照 context_snapshot（JSON）</label>
        <textarea id="sim-snapshot" placeholder='{"地点类型":"酒楼","境界":"凡人","金钱":10,"年龄":20}'></textarea>
        <div class="row2">
          <div><label>抽样次数</label><input type="number" id="sim-n" value="100" /></div>
          <div style="display:flex; align-items:flex-end;"><button class="btn" onclick="runSimulate()">跑一遍</button></div>
        </div>
      </fieldset>
    </div>
    <div class="col">
      <fieldset>
        <legend>结果</legend>
        <pre class="result" id="sim-result">（还没跑过）</pre>
      </fieldset>
    </div>
  </div>
</div>

</div><!-- #content -->

<script>
// ---------- 通用 ----------
function $(id) { return document.getElementById(id); }
function csvToArr(s) { return s.split(",").map(x => x.trim()).filter(Boolean); }
function arrToCsv(a) { return (a || []).join(", "); }
function jsonOrNull(text) {
  const t = (text || "").trim();
  if (!t) return null;
  return JSON.parse(t);
}
async function api(method, url, body) {
  const res = await fetch(url, {
    method, headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok && res.status !== 200) {
    return { ok: false, field_errors: [{ field: "http", message: data.detail || res.statusText }] };
  }
  return data;
}
function renderErrors(el, errors) {
  el.textContent = (errors || []).map(e => `${e.field}: ${e.message}`).join("\\n");
}

// ---------- 左侧菜单切换 ----------
document.querySelectorAll(".menu-item").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".menu-item").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".pane").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    $("pane-" + btn.dataset.pane).classList.add("active");
  });
});

// ---------- 地图（可视化编辑器，2 级下钻：顶层 <-> 子地点） ----------
// 新增/编辑地点、新增/编辑路线都走独立弹窗（.modal-overlay），不占画布/列表的地方；
// 画布右侧固定显示当前层级的地点列表 + 路线列表。
const SVG_NS = "http://www.w3.org/2000/svg";
let locations = [];
let routes = [];
let mapParentId = null;          // 当前所在层级的父 id；null = 顶层
let mapBreadcrumbStack = [];     // [{id, name}, ...]，下钻路径
let mapSelectedId = null;        // 当前选中（高亮/待编辑）的地点
let mapConnectMode = false;
let mapConnectFirst = null;      // 连接路线模式下先点的第一个节点

async function loadMap() {
  locations = await api("GET", "/api/admin/locations");
  routes = await api("GET", "/api/admin/routes");
  refreshMapView();
}

function refreshMapView() {
  renderMapCanvas();
  renderLocationList();
  renderRouteTable();
}

function currentLevelLocations() {
  return locations.filter(l => (l.parent_location_id || null) === mapParentId);
}

function nodePosition(loc, indexInLevel) {
  if (loc.x || loc.y) return { x: loc.x, y: loc.y };
  const cols = 5;
  const col = indexInLevel % cols, row = Math.floor(indexInLevel / cols);
  return { x: 90 + col * 150, y: 70 + row * 110 };
}

const NODE_RADIUS = 22;
const NODE_MIN_DISTANCE = NODE_RADIUS * 2 + 20; // 圆心最小间距：两个半径 + 一点边距，不然圆挨在一起也算"重叠"
const CANVAS_W = 900, CANVAS_H = 480, CANVAS_MARGIN = 34;

// 网格兜底位置只按"当前层级第几个节点"算坐标，不知道其它节点是不是已经手动拖到了
// 同一个格子上；手动拖拽也完全可能把两个节点拖到几乎同一个点。这里做几轮简单的
// 圆形碰撞松弛：两个节点圆心距离小于 NODE_MIN_DISTANCE 就沿连线互相推开，直到不再
// 重叠（或达到迭代上限），再夹回画布范围内，避免推到边界外。
function resolveCollisions(posOf, ids) {
  for (let iter = 0; iter < 12; iter++) {
    let moved = false;
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        const a = posOf[ids[i]], b = posOf[ids[j]];
        let dx = b.x - a.x, dy = b.y - a.y;
        let dist = Math.hypot(dx, dy);
        if (dist < NODE_MIN_DISTANCE) {
          moved = true;
          if (dist < 0.01) {
            // 完全重合时按 (i,j) 错开摆脱角度（黄金角式取值），让好几个重合的节点
            // 各自往不同方向散开，不会全部只沿同一根轴推来推去、越推越乱。
            const angle = (i * 2.399963 + j * 0.618034) * Math.PI;
            dx = Math.cos(angle); dy = Math.sin(angle); dist = 1;
          }
          const push = (NODE_MIN_DISTANCE - dist) / 2;
          const ux = dx / dist, uy = dy / dist;
          a.x -= ux * push; a.y -= uy * push;
          b.x += ux * push; b.y += uy * push;
        }
      }
    }
    if (!moved) break;
  }
  for (const id of ids) {
    const p = posOf[id];
    p.x = Math.max(CANVAS_MARGIN, Math.min(CANVAS_W - CANVAS_MARGIN, p.x));
    p.y = Math.max(CANVAS_MARGIN, Math.min(CANVAS_H - CANVAS_MARGIN, p.y));
  }
}

function svgPoint(evt) {
  const svg = $("map-canvas");
  const pt = svg.createSVGPoint();
  pt.x = evt.clientX; pt.y = evt.clientY;
  return pt.matrixTransform(svg.getScreenCTM().inverse());
}

function renderBreadcrumb() {
  let html = '<button onclick="goToMapRoot()">顶层</button>';
  mapBreadcrumbStack.forEach((entry, i) => {
    const isLast = i === mapBreadcrumbStack.length - 1;
    html += " / " + (isLast
      ? `<span class="current">${entry.name}</span>`
      : `<button onclick="goToMapLevel(${i})">${entry.name}</button>`);
  });
  $("map-breadcrumb").innerHTML = html;
}

function goToMapRoot() {
  mapBreadcrumbStack = []; mapParentId = null; mapSelectedId = null;
  refreshMapView();
}
function goToMapLevel(i) {
  const entry = mapBreadcrumbStack[i];
  mapBreadcrumbStack = mapBreadcrumbStack.slice(0, i + 1);
  mapParentId = entry.id; mapSelectedId = null;
  refreshMapView();
}
function drillInto(loc) {
  mapBreadcrumbStack.push({ id: loc.location_id, name: loc.name || loc.location_id });
  mapParentId = loc.location_id; mapSelectedId = null;
  refreshMapView();
}

function renderMapCanvas() {
  renderBreadcrumb();
  const svg = $("map-canvas");
  svg.innerHTML = "";
  const levelLocs = currentLevelLocations();
  const idSet = new Set(levelLocs.map(l => l.location_id));
  const posOf = {};
  levelLocs.forEach((loc, i) => { posOf[loc.location_id] = nodePosition(loc, i); });
  resolveCollisions(posOf, levelLocs.map(l => l.location_id));

  for (const r of routes) {
    if (!idSet.has(r.from_id) || !idSet.has(r.to_id)) continue;
    const a = posOf[r.from_id], b = posOf[r.to_id];
    const line = document.createElementNS(SVG_NS, "line");
    line.setAttribute("x1", a.x); line.setAttribute("y1", a.y);
    line.setAttribute("x2", b.x); line.setAttribute("y2", b.y);
    line.setAttribute("class", "route-line" + (r.bidirectional ? "" : " one-way"));
    svg.appendChild(line);
  }

  // 点空白处取消选中：evt.target === svg 时才触发（点在节点上 target 是 circle，会被
  // 节点自己的 click 处理器 stopPropagation 挡住，不会落到这里）。画布左侧点击不弹
  // 窗——新建走工具栏/列表头的"+ 新建"按钮。
  svg.onclick = (evt) => {
    if (evt.target !== svg || mapConnectMode) return;
    if (mapSelectedId) { mapSelectedId = null; renderMapCanvas(); renderLocationList(); }
  };

  for (const loc of levelLocs) {
    const pos = posOf[loc.location_id];
    const circle = document.createElementNS(SVG_NS, "circle");
    circle.setAttribute("cx", pos.x); circle.setAttribute("cy", pos.y); circle.setAttribute("r", NODE_RADIUS);
    let cls = "node-circle";
    if (loc.hidden) cls += " hidden-loc";
    if (loc.location_id === mapSelectedId) cls += " selected";
    if (mapConnectMode && loc.location_id === mapConnectFirst) cls += " connect-first";
    circle.setAttribute("class", cls);

    const label = document.createElementNS(SVG_NS, "text");
    label.setAttribute("x", pos.x); label.setAttribute("y", pos.y + 36);
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("class", "node-label");
    label.textContent = loc.name || loc.location_id;

    svg.appendChild(circle); svg.appendChild(label);

    circle.addEventListener("click", (evt) => { evt.stopPropagation(); onNodeClick(loc); });
    circle.addEventListener("dblclick", (evt) => { evt.stopPropagation(); drillInto(loc); });
    circle.addEventListener("mousedown", (evt) => startDrag(evt, loc, circle, label));

    // 选中节点右上角的删除角标：不用先打开弹窗，画布上直接删。
    if (loc.location_id === mapSelectedId) {
      const delBtn = document.createElementNS(SVG_NS, "g");
      delBtn.setAttribute("class", "node-delete-btn");
      const delCircle = document.createElementNS(SVG_NS, "circle");
      delCircle.setAttribute("cx", pos.x + 18); delCircle.setAttribute("cy", pos.y - 18); delCircle.setAttribute("r", 8);
      const delMark = document.createElementNS(SVG_NS, "text");
      delMark.setAttribute("x", pos.x + 18); delMark.setAttribute("y", pos.y - 14);
      delMark.setAttribute("text-anchor", "middle");
      delMark.textContent = "×";
      delBtn.appendChild(delCircle); delBtn.appendChild(delMark);
      delBtn.addEventListener("click", (evt) => { evt.stopPropagation(); deleteLocation(loc.location_id); });
      svg.appendChild(delBtn);
    }
  }
}

function onNodeClick(loc) {
  if (suppressNextClick) { suppressNextClick = false; return; }
  if (mapConnectMode) {
    if (!mapConnectFirst) { mapConnectFirst = loc.location_id; renderMapCanvas(); return; }
    if (mapConnectFirst === loc.location_id) { mapConnectFirst = null; renderMapCanvas(); return; }
    const from_id = mapConnectFirst, to_id = loc.location_id;
    mapConnectFirst = null;
    renderMapCanvas();
    // 连线本身也走独立弹窗确认耗时/是否双向，不直接落库。
    openRouteModal({ from_id, to_id, move_cost_shichen: 1, bidirectional: true });
    return;
  }
  // 左侧画布点击只负责选中/高亮，不弹编辑框——编辑走右侧列表（点行或"编辑"按钮）。
  mapSelectedId = loc.location_id;
  renderMapCanvas();
  renderLocationList();
}

let dragState = null;
let suppressNextClick = false;  // 拖动结束后，浏览器仍会在原节点上补一个 click——
// 用这个标记吞掉那一次，不然选中状态会被拖动前的旧数据闪一下再刷新回来。
const DRAG_THRESHOLD = 3; // 像素；低于这个位移量按"点击"处理，不当拖动存盘

function startDrag(evt, loc, circle, label) {
  if (mapConnectMode) return;
  evt.preventDefault(); evt.stopPropagation();
  const startPoint = svgPoint(evt);
  let moved = false;
  dragState = { loc };
  const move = (e) => {
    if (!dragState) return;
    const p = svgPoint(e);
    if (!moved && Math.hypot(p.x - startPoint.x, p.y - startPoint.y) > DRAG_THRESHOLD) moved = true;
    circle.setAttribute("cx", p.x); circle.setAttribute("cy", p.y);
    label.setAttribute("x", p.x); label.setAttribute("y", p.y + 36);
    dragState.lastPoint = p;
  };
  const up = async () => {
    document.removeEventListener("mousemove", move);
    document.removeEventListener("mouseup", up);
    if (moved && dragState && dragState.lastPoint) {
      suppressNextClick = true;
      const updated = Object.assign({}, dragState.loc, {
        x: Math.round(dragState.lastPoint.x), y: Math.round(dragState.lastPoint.y),
      });
      await api("POST", "/api/admin/locations", updated);
      await loadMap();
    }
    dragState = null;
  };
  document.addEventListener("mousemove", move);
  document.addEventListener("mouseup", up);
}

function toggleConnectMode() {
  mapConnectMode = !mapConnectMode;
  mapConnectFirst = null;
  $("map-connect-btn").classList.toggle("toggled", mapConnectMode);
  renderMapCanvas();
}

function renderLocationList() {
  const body = document.querySelector("#location-table tbody");
  body.innerHTML = "";
  for (const loc of currentLevelLocations()) {
    const tr = document.createElement("tr");
    if (loc.location_id === mapSelectedId) tr.classList.add("row-selected");
    tr.innerHTML = `<td>${loc.location_id}</td><td>${loc.name}</td><td>${loc.location_type}</td><td></td>`;
    const actionsTd = tr.lastElementChild;
    const editBtn = document.createElement("button");
    editBtn.className = "btn secondary"; editBtn.textContent = "编辑";
    editBtn.addEventListener("click", (evt) => { evt.stopPropagation(); openLocationModal(loc); });
    const delBtn = document.createElement("button");
    delBtn.className = "btn secondary"; delBtn.textContent = "删除";
    delBtn.addEventListener("click", (evt) => { evt.stopPropagation(); deleteLocation(loc.location_id); });
    actionsTd.appendChild(editBtn); actionsTd.appendChild(delBtn);
    // 点行本身也直接打开编辑弹窗——这是"右侧"的交互，跟左侧画布点击（只选中）不冲突。
    tr.addEventListener("click", () => openLocationModal(loc));
    body.appendChild(tr);
  }
}

function renderRouteTable() {
  const idSet = new Set(currentLevelLocations().map(l => l.location_id));
  const body = document.querySelector("#route-table tbody");
  body.innerHTML = "";
  for (const r of routes) {
    if (!idSet.has(r.from_id) || !idSet.has(r.to_id)) continue;
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${r.from_id}</td><td>${r.to_id}</td><td>${r.move_cost_shichen}</td><td>${r.bidirectional ? "是" : "否"}</td>` +
      `<td><button class="btn secondary" onclick="event.stopPropagation(); deleteRoute('${r.from_id}','${r.to_id}')">删除</button></td>`;
    tr.addEventListener("click", () => openRouteModal(r));
    body.appendChild(tr);
  }
}

// ---------- 地点弹窗 ----------
function fillLocationForm(loc) {
  $("loc-id").value = loc.location_id; $("loc-name").value = loc.name;
  $("loc-kind").value = loc.kind; $("loc-type").value = loc.location_type;
  $("loc-qi").value = loc.qi_density; $("loc-danger").value = loc.danger_level;
  $("loc-condition").value = loc.condition; $("loc-parent").value = loc.parent_location_id || "";
  $("loc-x").value = loc.x; $("loc-y").value = loc.y;
  $("loc-hidden").checked = loc.hidden; $("loc-concealment").value = loc.concealment;
  $("loc-discovered").checked = loc.discovered;
  $("loc-delete-btn").style.display = "";
}
function resetLocationForm() {
  for (const id of ["loc-id","loc-name","loc-type"]) $(id).value = "";
  $("loc-kind").value = "城市"; $("loc-qi").value = "1.0"; $("loc-danger").value = "0";
  $("loc-condition").value = "完好"; $("loc-hidden").checked = false;
  $("loc-concealment").value = "0"; $("loc-discovered").checked = false;
  $("loc-x").value = "0"; $("loc-y").value = "0";
  $("loc-parent").value = mapParentId || "";
  $("loc-errors").textContent = "";
  $("loc-delete-btn").style.display = "none";
}

function openLocationModal(loc, coords) {
  mapSelectedId = loc ? loc.location_id : null;
  if (loc) {
    fillLocationForm(loc);
    $("location-modal-title").textContent = "编辑地点：" + loc.location_id;
  } else {
    resetLocationForm();
    if (coords) { $("loc-x").value = Math.round(coords.x); $("loc-y").value = Math.round(coords.y); }
    $("location-modal-title").textContent = "新增地点";
  }
  renderMapCanvas(); renderLocationList();
  $("location-modal-overlay").classList.add("open");
  if (!loc) $("loc-id").focus();
}
function closeLocationModal() {
  $("location-modal-overlay").classList.remove("open");
}

async function saveLocation() {
  const dto = {
    location_id: $("loc-id").value.trim(), name: $("loc-name").value.trim(),
    kind: $("loc-kind").value, location_type: $("loc-type").value.trim(),
    qi_density: parseFloat($("loc-qi").value) || 0, danger_level: parseFloat($("loc-danger").value) || 0,
    condition: $("loc-condition").value, parent_location_id: $("loc-parent").value.trim() || null,
    x: parseFloat($("loc-x").value) || 0, y: parseFloat($("loc-y").value) || 0,
    hidden: $("loc-hidden").checked, concealment: parseFloat($("loc-concealment").value) || 0,
    discovered: $("loc-discovered").checked,
  };
  if (!dto.location_id || !dto.location_type) {
    renderErrors($("loc-errors"), [{ field: "location_id/location_type", message: "必填" }]);
    return;
  }
  const resp = await api("POST", "/api/admin/locations", dto);
  renderErrors($("loc-errors"), resp.field_errors);
  if (resp.ok) {
    mapSelectedId = dto.location_id;
    closeLocationModal();
    await loadMap();
  }
}

async function deleteLocation(id) {
  if (!id) return;
  if (!confirm(`删除地点 ${id}？相关路线也会一并删除。`)) return;
  await api("DELETE", `/api/admin/locations/${encodeURIComponent(id)}`);
  mapSelectedId = null;
  closeLocationModal();
  await loadMap();
}

// ---------- 路线弹窗 ----------
function openRouteModal(route) {
  if (route) {
    $("route-from").value = route.from_id; $("route-to").value = route.to_id;
    $("route-cost").value = route.move_cost_shichen; $("route-bidir").checked = route.bidirectional;
    $("route-modal-title").textContent = `路线：${route.from_id} → ${route.to_id}`;
  } else {
    $("route-from").value = ""; $("route-to").value = "";
    $("route-cost").value = "1"; $("route-bidir").checked = true;
    $("route-modal-title").textContent = "新增路线";
  }
  $("route-errors").textContent = "";
  $("route-modal-overlay").classList.add("open");
}
function closeRouteModal() {
  $("route-modal-overlay").classList.remove("open");
}

async function saveRoute() {
  const dto = {
    from_id: $("route-from").value.trim(), to_id: $("route-to").value.trim(),
    move_cost_shichen: parseInt($("route-cost").value) || 0, bidirectional: $("route-bidir").checked,
  };
  const resp = await api("POST", "/api/admin/routes", dto);
  renderErrors($("route-errors"), resp.field_errors);
  if (resp.ok) { closeRouteModal(); await loadMap(); }
}

async function deleteRoute(from_id, to_id) {
  await api("DELETE", `/api/admin/routes?from_id=${encodeURIComponent(from_id)}&to_id=${encodeURIComponent(to_id)}`);
  await loadMap();
}

// 点弹窗背景关闭；Esc 关闭所有弹窗
document.querySelectorAll(".modal-overlay").forEach(overlay => {
  overlay.addEventListener("click", (evt) => { if (evt.target === overlay) overlay.classList.remove("open"); });
});

// ---------- 物品 ----------
let items = [];

async function loadItems() {
  items = await api("GET", "/api/admin/items");
  const body = document.querySelector("#item-table tbody");
  body.innerHTML = "";
  for (const it of items) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${it.item_id}</td><td>${it.name}</td><td>${it.kind}</td><td>${it.description}</td>` +
      `<td><button class="btn secondary" onclick="event.stopPropagation(); deleteItem('${it.item_id}')">删除</button></td>`;
    tr.addEventListener("click", () => fillItemForm(it));
    body.appendChild(tr);
  }
}

function fillItemForm(it) {
  $("item-id").value = it.item_id; $("item-name").value = it.name;
  $("item-kind").value = it.kind; $("item-desc").value = it.description;
  $("item-stackable").checked = it.stackable; $("item-unique").checked = it.unique;
}
function clearItemForm() {
  $("item-id").value = ""; $("item-name").value = ""; $("item-desc").value = "";
  $("item-kind").value = "material"; $("item-stackable").checked = true; $("item-unique").checked = false;
  $("item-errors").textContent = "";
}

async function saveItem() {
  const dto = {
    item_id: $("item-id").value.trim(), name: $("item-name").value.trim(),
    kind: $("item-kind").value, description: $("item-desc").value,
    stackable: $("item-stackable").checked, unique: $("item-unique").checked,
  };
  if (!dto.item_id) { renderErrors($("item-errors"), [{ field: "item_id", message: "必填" }]); return; }
  const resp = await api("POST", "/api/admin/items", dto);
  renderErrors($("item-errors"), resp.field_errors);
  if (resp.ok) { await loadItems(); }
}

async function deleteItem(id) {
  if (!confirm(`删除物品 ${id}？`)) return;
  await api("DELETE", `/api/admin/items/${encodeURIComponent(id)}`);
  await loadItems();
}

// ---------- 事件 ----------
let events = [];

async function loadEvents() {
  events = await api("GET", "/api/admin/events");
  renderEventList();
}

function renderEventList() {
  const q = ($("event-search").value || "").toLowerCase();
  const body = $("event-list");
  body.innerHTML = "";
  for (const e of events) {
    const hay = (e.event_id + " " + e.tags.join(" ")).toLowerCase();
    if (q && !hay.includes(q)) continue;
    const tr = document.createElement("tr");
    const badge = e.is_draft ? '<span class="badge draft">草稿</span>' : '<span class="badge published">已发布</span>';
    tr.innerHTML = `<td>${e.event_id}<br/>${badge} ${e.tags.join(",")}</td>`;
    tr.addEventListener("click", () => loadEventDetail(e.event_id));
    body.appendChild(tr);
  }
}

async function loadEventDetail(id) {
  const d = await api("GET", `/api/admin/events/${encodeURIComponent(id)}`);
  $("ev-id").value = d.event_id; $("ev-priority").value = d.priority;
  $("ev-locations").value = arrToCsv(d.applicable_locations);
  $("ev-time").value = arrToCsv(d.applicable_time);
  $("ev-weight").value = d.weight; $("ev-duration").value = d.duration_shichen;
  $("ev-cooldown").value = d.cooldown_shichen; $("ev-max-trigger").value = d.max_trigger_per_agent ?? "";
  $("ev-tags").value = arrToCsv(d.tags); $("ev-exclusive").value = arrToCsv(d.exclusive_tags);
  $("ev-aliases").value = arrToCsv(d.aliases); $("ev-scenario-ref").value = d.scenario_ref || "";
  $("ev-is-command").checked = d.is_command; $("ev-is-draft").checked = d.is_draft;
  $("ev-predicate").value = d.predicate ? JSON.stringify(d.predicate, null, 2) : "";
  $("ev-results").value = JSON.stringify(d.result_pool || [], null, 2);
  $("ev-variants").value = JSON.stringify(d.variants || [], null, 2);
  $("ev-reply-options").value = JSON.stringify(d.reply_options || [], null, 2);
  $("ev-errors").textContent = ""; $("ev-ok").textContent = "";
  $("sim-event-id").value = d.event_id;
}

function clearEventForm() {
  for (const id of ["ev-id","ev-time","ev-max-trigger","ev-tags","ev-exclusive","ev-aliases","ev-scenario-ref",
                     "ev-predicate","ev-results","ev-variants","ev-reply-options"]) $(id).value = "";
  $("ev-locations").value = "*"; $("ev-priority").value = "5"; $("ev-weight").value = "1.0";
  $("ev-duration").value = "1"; $("ev-cooldown").value = "0";
  $("ev-is-command").checked = false; $("ev-is-draft").checked = true;
  $("ev-errors").textContent = ""; $("ev-ok").textContent = "";
}

function buildEventDto() {
  return {
    event_id: $("ev-id").value.trim(),
    applicable_locations: csvToArr($("ev-locations").value) || ["*"],
    applicable_time: $("ev-time").value.trim() ? csvToArr($("ev-time").value).map(Number) : null,
    predicate: jsonOrNull($("ev-predicate").value),
    weight: parseFloat($("ev-weight").value) || 0,
    duration_shichen: parseInt($("ev-duration").value) || 0,
    cooldown_shichen: parseInt($("ev-cooldown").value) || 0,
    max_trigger_per_agent: $("ev-max-trigger").value.trim() ? parseInt($("ev-max-trigger").value) : null,
    exclusive_tags: csvToArr($("ev-exclusive").value),
    priority: parseInt($("ev-priority").value) || 5,
    tags: csvToArr($("ev-tags").value),
    aliases: csvToArr($("ev-aliases").value),
    result_pool: jsonOrNull($("ev-results").value) || [],
    variants: jsonOrNull($("ev-variants").value) || [],
    reply_options: jsonOrNull($("ev-reply-options").value) || [],
    scenario_ref: $("ev-scenario-ref").value.trim() || null,
    is_command: $("ev-is-command").checked,
    is_draft: $("ev-is-draft").checked,
  };
}

async function saveEvent() {
  $("ev-ok").textContent = "";
  let dto;
  try { dto = buildEventDto(); }
  catch (e) { renderErrors($("ev-errors"), [{ field: "json", message: "JSON 格式错误：" + e.message }]); return; }
  const resp = await api("POST", "/api/admin/events", dto);
  renderErrors($("ev-errors"), resp.field_errors);
  if (resp.ok) {
    $("ev-ok").textContent = "已保存：" + resp.event_id;
    $("sim-event-id").value = resp.event_id;
    await loadEvents();
  }
}

async function publishEvent() {
  const id = $("ev-id").value.trim();
  if (!id) return;
  await saveEvent();
  const resp = await api("POST", `/api/admin/events/${encodeURIComponent(id)}/publish`, {});
  if (resp.ok) { $("ev-ok").textContent = "已发布：" + id; $("ev-is-draft").checked = false; await loadEvents(); }
}

async function unpublishEvent() {
  const id = $("ev-id").value.trim();
  if (!id) return;
  const resp = await api("POST", `/api/admin/events/${encodeURIComponent(id)}/unpublish`, {});
  if (resp.ok) { $("ev-ok").textContent = "已撤回为草稿：" + id; $("ev-is-draft").checked = true; await loadEvents(); }
}

async function deleteEvent() {
  const id = $("ev-id").value.trim();
  if (!id || !confirm(`删除事件 ${id}？`)) return;
  await api("DELETE", `/api/admin/events/${encodeURIComponent(id)}`);
  clearEventForm();
  await loadEvents();
}

// ---------- 模拟触发 ----------
async function runSimulate() {
  const id = $("sim-event-id").value.trim();
  if (!id) { $("sim-result").textContent = "先填 event_id。"; return; }
  let snapshot;
  try { snapshot = jsonOrNull($("sim-snapshot").value) || {}; }
  catch (e) { $("sim-result").textContent = "快照 JSON 格式错误：" + e.message; return; }
  const resp = await api("POST", "/api/admin/simulate", {
    event_id: id, context_snapshot: snapshot, sample_n: parseInt($("sim-n").value) || 100,
  });
  $("sim-result").textContent = JSON.stringify(resp, null, 2);
}

// Esc 关闭弹窗；选中节点后按 Delete/Backspace 直接删——前提是焦点不在输入框里
// （否则没法正常删字），且没有弹窗开着（开着交给弹窗里的删除按钮，避免手滑误删）。
document.addEventListener("keydown", (evt) => {
  if (evt.key === "Escape") {
    document.querySelectorAll(".modal-overlay.open").forEach(o => o.classList.remove("open"));
    return;
  }
  if (evt.key !== "Delete" && evt.key !== "Backspace") return;
  const tag = (document.activeElement && document.activeElement.tagName) || "";
  if (["INPUT", "TEXTAREA", "SELECT"].includes(tag)) return;
  if (document.querySelector(".modal-overlay.open")) return;
  if (!mapSelectedId) return;
  if (!$("pane-mapeditor").classList.contains("active")) return;
  evt.preventDefault();
  deleteLocation(mapSelectedId);
});

loadMap();
loadItems();
loadEvents();
</script>
</body>
</html>
"""


def render_admin_page() -> str:
    return PAGE_HTML
