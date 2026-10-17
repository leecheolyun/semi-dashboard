(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const state = { view: "companies", topic: "all", seg: "all", region: "all", q: "", sort: "default", data: null };
  const REGION = { all: "전체", KR: "국내", GLOBAL: "해외" };
  const LANG_REGION = { ko: "KR", en: "GLOBAL" };
  const CUR = { KRW: "원", USD: "$", JPY: "¥", TWD: "NT$", EUR: "€" };

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const cls = (v) => (v == null || Math.abs(v) < 0.005 ? "flat" : v > 0 ? "up" : "down");
  const arrow = (v) => (v == null || Math.abs(v) < 0.005 ? "–" : v > 0 ? "▲" : "▼");
  const pct = (v) => (v == null ? "-" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`);

  function fmtPrice(v, cur) {
    if (v == null) return "-";
    const d = cur === "KRW" || cur === "JPY" ? 0 : v >= 1000 ? 1 : 2;
    const n = v.toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d });
    if (cur === "KRW") return `${n}<small>원</small>`;
    return `${n}<small>${esc(cur || "")}</small>`;
  }
  function fmtAbs(v, cur) {
    if (v == null) return "";
    const d = cur === "KRW" || cur === "JPY" ? 0 : 2;
    return (v > 0 ? "+" : "") + v.toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  function rel(iso) {
    if (!iso) return "";
    const s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 60) return "방금";
    if (s < 3600) return `${Math.floor(s / 60)}분 전`;
    if (s < 86400) return `${Math.floor(s / 3600)}시간 전`;
    if (s < 86400 * 7) return `${Math.floor(s / 86400)}일 전`;
    return new Date(iso).toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
  }
  const kst = (iso) => new Date(iso).toLocaleString("ko-KR", { timeZone: "Asia/Seoul", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }) + " KST";

  function spark(closes, change) {
    if (!closes || closes.length < 2) return "";
    const w = 120, h = 40, p = 3;
    const ys = closes.map((c) => c[1]);
    const min = Math.min(...ys), max = Math.max(...ys), span = max - min || 1;
    const pts = ys.map((y, i) => [p + (i * (w - 2 * p)) / (ys.length - 1), h - p - ((y - min) / span) * (h - 2 * p)]);
    const line = pts.map((q, i) => `${i ? "L" : "M"}${q[0].toFixed(1)},${q[1].toFixed(1)}`).join("");
    const area = `${line}L${pts.at(-1)[0].toFixed(1)},${h}L${pts[0][0].toFixed(1)},${h}Z`;
    const c = cls(change);
    const color = c === "up" ? "var(--up)" : c === "down" ? "var(--down)" : "var(--flat)";
    const id = "g" + Math.random().toString(36).slice(2, 8);
    return `<svg class="spark" viewBox="0 0 ${w} ${h}" role="img" aria-label="3개월 추이 ${pct(change)}">
      <defs><linearGradient id="${id}" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${color}" stop-opacity=".25"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>
      <path d="${area}" fill="url(#${id})"/><path d="${line}" fill="none" stroke="${color}" stroke-width="1.6" stroke-linejoin="round"/>
      <circle cx="${pts.at(-1)[0].toFixed(1)}" cy="${pts.at(-1)[1].toFixed(1)}" r="2.4" fill="${color}"/></svg>`;
  }

  function matches(c) {
    if (state.seg !== "all" && c.segment !== state.seg) return false;
    if (state.region !== "all" && c.region !== state.region) return false;
    if (!state.q) return true;
    const q = state.q.toLowerCase();
    const hay = [c.name, c.name_en, c.ticker, ...(c.alt_tickers || []), ...(c.news || []).map((n) => n.title)].join(" ").toLowerCase();
    return hay.includes(q);
  }

  function newsItem(n) {
    return `<li><a href="${esc(n.link)}" target="_blank" rel="noopener" title="${esc(n.title)}">${esc(n.title)}</a>
      <div class="src">${esc(n.source)} · ${rel(n.published)}</div></li>`;
  }

  function card(c) {
    const q = c.quote;
    const news = c.news || [];
    const segName = (state.data.segments.find((s) => s.id === c.segment) || {}).name || "";
    let priceBlock;
    if (q) {
      priceBlock = `<div class="price-row">
          <div><div class="price">${fmtPrice(q.price, q.currency)}</div>
          <div class="chg ${cls(q.change_pct)}">${arrow(q.change_pct)} ${fmtAbs(q.change, q.currency)} <span class="pill ${cls(q.change_pct)}">${pct(q.change_pct)}</span></div></div>
          ${spark(q.closes, q.change_3m_pct)}
        </div>
        <div class="range"><span>3M 저 ${fmtAbs(q.low_3m, q.currency).replace("+", "")}</span><span class="${cls(q.change_3m_pct)}">3M ${pct(q.change_3m_pct)}</span><span>3M 고 ${fmtAbs(q.high_3m, q.currency).replace("+", "")}</span></div>`;
    } else {
      priceBlock = `<div class="note">${esc(c.note || "시세 정보 없음")}</div>`;
    }
    const alts = (c.alt_quotes || []).map((a) => `<div class="alt">${esc(a.ticker)} ${fmtPrice(a.price, a.currency).replace(/<\/?small>/g, " ")} <span class="${cls(a.change_pct)}">${pct(a.change_pct)}</span></div>`).join("");
    const stale = c.quote_stale || c.news_stale ? `<div class="stale">⚠ 일부 데이터 갱신 실패 (이전 값 표시)</div>` : "";
    const first = news.slice(0, 4).map(newsItem).join("");
    const rest = news.slice(4).map(newsItem).join("");
    return `<article class="card" data-id="${esc(c.id)}">
      <div class="card-head"><div>
        <div class="cname">${esc(c.name)}</div>
        <div class="cmeta"><span>${esc(c.name_en || "")}</span></div>
        <div class="cmeta" style="margin-top:3px"><span class="badge ${c.region === "KR" ? "kr" : ""}">${REGION[c.region]}</span>${c.ticker ? `<span class="badge">${esc(c.ticker)}</span>` : ""}${q && q.exchange ? `<span>${esc(q.exchange)}</span>` : ""}</div>
      </div></div>
      ${priceBlock}${alts}${stale}
      ${news.length ? `<ul class="news">${first}</ul>${rest ? `<details><summary>뉴스 ${news.length - 4}건 더 보기</summary><ul class="news">${rest}</ul></details>` : ""}` : `<div class="note">최근 뉴스 없음</div>`}
    </article>`;
  }

  function sortList(list) {
    const val = (c, k) => (c.quote ? c.quote[k] : null);
    const by = {
      chg_desc: (a, b) => (val(b, "change_pct") ?? -1e9) - (val(a, "change_pct") ?? -1e9),
      chg_asc: (a, b) => (val(a, "change_pct") ?? 1e9) - (val(b, "change_pct") ?? 1e9),
      m3_desc: (a, b) => (val(b, "change_3m_pct") ?? -1e9) - (val(a, "change_3m_pct") ?? -1e9),
      news: (a, b) => ((b.news[0] || {}).published || "").localeCompare((a.news[0] || {}).published || ""),
    }[state.sort];
    return by ? [...list].sort(by) : list;
  }

  function renderCompanies(list) {
    const el = $("#companies");
    if (!list.length) { el.innerHTML = `<div class="empty">조건에 맞는 기업이 없습니다.</div>`; return; }
    const segs = state.data.segments.filter((s) => state.seg === "all" || s.id === state.seg);
    el.innerHTML = segs.map((s) => {
      const items = sortList(list.filter((c) => c.segment === s.id));
      if (!items.length) return "";
      return `<div class="seg-block"><div class="seg-title"><h2>${esc(s.name)}</h2><span class="muted">${esc(s.desc || "")} · ${items.length}개</span></div>
        <div class="grid">${items.map(card).join("")}</div></div>`;
    }).join("");
  }

  function renderFeed(list) {
    const seen = new Set(); const all = [];
    for (const c of list) for (const n of c.news || []) {
      const k = n.title.replace(/\W/g, "").toLowerCase().slice(0, 60);
      if (seen.has(k)) { const ex = all.find((x) => x.k === k); if (ex && !ex.cos.includes(c)) ex.cos.push(c); continue; }
      seen.add(k); all.push({ ...n, k, cos: [c] });
    }
    all.sort((a, b) => (b.published || "").localeCompare(a.published || ""));
    const top = all.slice(0, 60);
    $("#feedCount").textContent = `${top.length}건`;
    $("#feed").innerHTML = top.length ? top.map((n) => `<li>
      <a class="ft" href="${esc(n.link)}" target="_blank" rel="noopener">${esc(n.title)}</a>
      <div class="fm">${n.cos.map((c) => `<button class="tag" data-q="${esc(c.name)}">${esc(c.name)}</button>`).join("")}<span>${esc(n.source)}</span><span>· ${rel(n.published)}</span></div></li>`).join("")
      : `<li class="empty">뉴스 없음</li>`;
    if (!document.getElementById("feedMore")) $(".feed").insertAdjacentHTML("beforeend", `<button class="feed-more" id="feedMore" data-view="news">업계 뉴스 (HBM · 기판 · 패키징 …) 보기 →</button>`);
  }

  function renderSummary() {
    const d = state.data;
    $("#summary").innerHTML = d.segments.map((s) => {
      const cs = d.companies.filter((c) => c.segment === s.id && (state.region === "all" || c.region === state.region) && c.quote);
      const ch = cs.map((c) => c.quote.change_pct).filter((v) => v != null);
      const avg = ch.length ? ch.reduce((a, b) => a + b, 0) / ch.length : null;
      const up = ch.filter((v) => v > 0).length, dn = ch.filter((v) => v < 0).length;
      return `<button class="sum ${state.seg === s.id ? "active" : ""}" data-seg="${s.id}" type="button">
        <div class="t">${esc(s.name)} 평균 등락</div>
        <div class="v ${cls(avg)}">${pct(avg)}</div>
        <div class="b"><span class="up">▲${up}</span> · <span class="down">▼${dn}</span> · ${cs.length}종목</div></button>`;
    }).join("");
  }

  function renderChips() {
    const d = state.data;
    const cnt = (seg) => d.companies.filter((c) => (seg === "all" || c.segment === seg) && (state.region === "all" || c.region === state.region)).length;
    $("#segChips").innerHTML = [{ id: "all", name: "전체" }, ...d.segments].map((s, i) =>
      `<button class="chip ${i === 1 ? "star" : ""}" data-seg="${s.id}" aria-pressed="${state.seg === s.id}">${esc(s.name)}<span class="n">${cnt(s.id)}</span></button>`).join("");
    $("#regionChips").innerHTML = Object.entries(REGION).map(([k, v]) =>
      `<button class="chip" data-region="${k}" aria-pressed="${state.region === k}">${v}</button>`).join("");
  }

  function topicItems() {
    const topics = (state.data.topics || []).filter((t) => state.topic === "all" || t.id === state.topic);
    const map = new Map();
    for (const t of topics) for (const n of t.news || []) {
      const k = n.title.replace(/\W/g, "").toLowerCase().slice(0, 60);
      if (map.has(k)) { const ex = map.get(k); if (!ex.topics.includes(t)) ex.topics.push(t); continue; }
      map.set(k, { ...n, topics: [t] });
    }
    const q = state.q.toLowerCase();
    return [...map.values()]
      .filter((n) => state.region === "all" || LANG_REGION[n.lang] === state.region)
      .filter((n) => !q || (n.title + " " + n.source).toLowerCase().includes(q))
      .sort((a, b) => (b.published || "").localeCompare(a.published || ""));
  }

  function renderTopics() {
    const topics = state.data.topics || [];
    const cnt = (id) => topics.filter((t) => id === "all" || t.id === id).reduce((a, t) => a + (t.news || []).filter((n) => state.region === "all" || LANG_REGION[n.lang] === state.region).length, 0);
    $("#topicChips").innerHTML = [{ id: "all", name: "전체 토픽" }, ...topics].map((t) =>
      `<button class="chip" data-topic="${esc(t.id)}" aria-pressed="${state.topic === t.id}">${esc(t.name)}${t.id === "all" ? "" : `<span class="n">${cnt(t.id)}</span>`}</button>`).join("");
    const items = topicItems();
    const cur = topics.find((t) => t.id === state.topic);
    $("#topicTitle").textContent = cur ? `업계 뉴스 · ${cur.name}` : "업계 뉴스 · 전체";
    $("#topicCount").textContent = `${items.length}건 · 최신순`;
    $("#topicNews").innerHTML = items.length ? items.map((n) => `<li>
      <a class="ft" href="${esc(n.link)}" target="_blank" rel="noopener">${esc(n.title)}</a>
      <div class="fm"><span class="lang">${n.lang === "ko" ? "KR" : "EN"}</span>${n.topics.map((t) => `<button class="tag topic" data-topic="${esc(t.id)}">#${esc(t.name)}</button>`).join("")}<span>${esc(n.source)}</span><span>· ${rel(n.published)}</span></div></li>`).join("")
      : `<li class="empty">조건에 맞는 뉴스가 없습니다.</li>`;
  }

  function render() {
    document.body.dataset.view = state.view;
    $("#tabCompanies").setAttribute("aria-selected", state.view === "companies");
    $("#tabNews").setAttribute("aria-selected", state.view === "news");
    $("#topicTotal").textContent = new Set((state.data.topics || []).flatMap((t) => (t.news || []).map((n) => n.title.replace(/\W/g, "").toLowerCase().slice(0, 60)))).size || "";
    const list = state.data.companies.filter(matches);
    if (state.view === "news") { renderChips(); renderTopics(); }
    else { renderChips(); renderSummary(); renderCompanies(list); renderFeed(list); }
    const p = new URLSearchParams();
    if (state.view !== "companies") p.set("view", state.view);
    if (state.view === "news" && state.topic !== "all") p.set("topic", state.topic);
    if (state.seg !== "all") p.set("seg", state.seg);
    if (state.region !== "all") p.set("region", state.region);
    if (state.q) p.set("q", state.q);
    history.replaceState(null, "", p.toString() ? `?${p}` : location.pathname);
  }

  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-seg],[data-region],[data-view],[data-topic],.tag");
    if (!t) return;
    if (t.dataset.view) { state.view = t.dataset.view; window.scrollTo(0, 0); }
    else if (t.dataset.topic) { state.view = "news"; state.topic = t.dataset.topic; }
    else if (t.classList.contains("tag")) { state.q = t.dataset.q; $("#q").value = state.q; }
    else if (t.dataset.seg) state.seg = state.seg === t.dataset.seg && t.dataset.seg !== "all" && t.classList.contains("sum") ? "all" : t.dataset.seg;
    else state.region = t.dataset.region;
    render();
  });
  let timer;
  $("#q").addEventListener("input", (e) => { clearTimeout(timer); timer = setTimeout(() => { state.q = e.target.value.trim(); render(); }, 150); });
  $("#sortSel").addEventListener("change", (e) => { state.sort = e.target.value; render(); });
  $("#themeBtn").addEventListener("click", () => {
    const root = document.documentElement;
    const cur = root.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    root.dataset.theme = cur === "dark" ? "light" : "dark";
    localStorage.setItem("theme", root.dataset.theme);
  });

  const p = new URLSearchParams(location.search);
  state.view = p.get("view") === "news" ? "news" : "companies"; state.topic = p.get("topic") || "all";
  state.seg = p.get("seg") || "all"; state.region = p.get("region") || "all"; state.q = p.get("q") || "";
  $("#q").value = state.q;

  fetch(`data/data.json?t=${Date.now()}`)
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((d) => {
      state.data = d;
      const s = d.stats || {};
      $("#updated").textContent = `업데이트 ${kst(d.generated_at)} · 기업 ${s.companies} · 시세 ${s.quotes_ok} · 뉴스 ${s.news_ok}`;
      render();
    })
    .catch((err) => {
      $("#updated").textContent = "데이터를 불러오지 못했습니다";
      $("#companies").innerHTML = `<div class="empty">data/data.json 로드 실패 (${esc(err.message)}). scripts/fetch.py 를 먼저 실행하세요.</div>`;
    });
})();
