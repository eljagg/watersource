/* WaterSource dashboards — generic renderer for the panel specifications in apps/reports/dashboards.py.
 *
 * One function per idiom (kpi, hbar, vbar, line, stacked, status, list). Colours come from CSS custom
 * properties (frontend/app.css: --ds-s1…--ds-s6, --ds-seq1…7, --ds-good/warn/serious/critical) so the same
 * chart definition renders correctly in light and dark mode; charts re-render when the theme toggles.
 * No inline event handlers, no eval: CSP stays "self" plus the page nonce.
 */
(function () {
  'use strict';
  const css = (k) => getComputedStyle(document.documentElement).getPropertyValue(k).trim();
  const SERIES = () => ['--ds-s1', '--ds-s2', '--ds-s3', '--ds-s4', '--ds-s5', '--ds-s6'].map(css);
  const SEQ = () => ['--ds-seq7', '--ds-seq6', '--ds-seq6', '--ds-seq5', '--ds-seq5', '--ds-seq4', '--ds-seq4', '--ds-seq3', '--ds-seq3', '--ds-seq2'].map(css);
  const STATUS = {
    much_below_normal: ['--ds-critical', 'Much below normal'], below_normal: ['--ds-serious', 'Below normal'], normal: ['--ds-s3', 'Normal'],
    above_normal: ['--ds-s1', 'Above normal'], much_above_normal: ['--ds-seq7', 'Much above normal'],
    no_recent_data: ['--ds-axis', 'No recent reading'], insufficient_record: ['--ds-axis', 'Record too short'],
    critical: ['--ds-critical'], serious: ['--ds-serious'], warn: ['--ds-warn'], good: ['--ds-good'], s1: ['--ds-s1'], s3: ['--ds-s3'],
  };
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const scale = () => parseFloat(css('--ds-scale')) || 1;
  const fs = (n) => Math.round(n * scale());

  const fmt = {
    int: (v) => (v == null ? '—' : Math.round(v).toLocaleString('en-JM')),
    pct: (v) => (v == null ? '—' : Number(v).toLocaleString('en-JM', { maximumFractionDigits: 1 })),
    days: (v) => (v == null ? '—' : Number(v).toLocaleString('en-JM', { maximumFractionDigits: 0 })),
    volume: (v) => (v == null ? '—' : v >= 1e6 ? (v / 1e6).toFixed(2) + ' M' : v >= 1e4 ? Math.round(v / 1e3).toLocaleString('en-JM') + ' k' : Math.round(v).toLocaleString('en-JM')),
    month: (iso) => { if (!iso) return ''; const d = new Date(iso); return MONTHS[d.getUTCMonth()] + (d.getUTCMonth() === 0 ? ' ' + String(d.getUTCFullYear()).slice(2) : ''); },
    label: (s) => { const t = String(s == null ? '' : s); return t.length <= 3 ? t.toUpperCase() : t.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase()); },
  };

  const base = () => ({ textStyle: { fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif', color: css('--ds-ink-2') }, animation: false });
  const tip = () => ({ trigger: 'axis', backgroundColor: css('--ds-surface'), borderColor: css('--ds-ring'), textStyle: { color: css('--ds-ink'), fontSize: fs(13) } });
  const axisCat = (cats, extra) => Object.assign({ type: 'category', data: cats, axisLine: { lineStyle: { color: css('--ds-axis') } }, axisTick: { show: false }, axisLabel: { color: css('--ds-muted'), fontSize: fs(12), margin: 10 } }, extra || {});
  const axisVal = (extra) => Object.assign({ type: 'value', splitLine: { lineStyle: { color: css('--ds-grid') } }, axisLabel: { color: css('--ds-muted'), fontSize: fs(12) }, axisLine: { show: false } }, extra || {});

  function sortRows(rows, key) {
    if (!key) return rows.slice();
    const desc = key.startsWith('-'); const k = desc ? key.slice(1) : key;
    return rows.slice().sort((a, b) => (a[k] > b[k] ? 1 : a[k] < b[k] ? -1 : 0) * (desc ? -1 : 1));
  }
  function sumBy(rows, label, value) {
    const m = new Map();
    rows.forEach((r) => m.set(r[label], (m.get(r[label]) || 0) + (Number(r[value]) || 0)));
    return [...m.entries()].map(([k, v]) => ({ [label]: k, [value]: v }));
  }

  // ---------------------------------------------------------------- idioms
  function hbar(el, rows, o) {
    let data = o.sum_by_label ? sumBy(rows, o.label, o.value) : rows;
    data = sortRows(data, o.sort || ('-' + o.value));
    if (o.limit) data = data.slice(0, o.limit);
    const labels = data.map((r) => fmt.label(r[o.label]));
    const values = data.map((r) => Number(r[o.value]) || 0);
    const seq = SEQ();
    const colour = (p) => (o.critical_above != null && p.value > o.critical_above) ? css('--ds-critical') : o.ranked ? seq[Math.min(p.dataIndex, seq.length - 1)] : css('--ds-s1');
    const f = fmt[o.fmt] || fmt.int;
    return {
      ...base(), tooltip: tip(), grid: { left: fs(o.label_width || 140) + 12, right: 64, top: 6, bottom: 6, containLabel: false },
      xAxis: axisVal({ splitLine: { show: false }, axisLabel: { show: false }, max: o.reference ? Math.max(o.reference * 1.3, ...values) : null }),
      yAxis: { type: 'category', inverse: true, data: labels, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: css('--ds-ink-2'), fontSize: fs(13), width: fs(o.label_width || 140), overflow: 'truncate' } },
      series: [{ type: 'bar', data: values, barWidth: fs(18), itemStyle: { color: colour, borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: 'right', color: css('--ds-ink'), fontSize: fs(13), fontWeight: 600, formatter: (p) => f(p.value) + (o.unit ? ' ' + o.unit : '') },
        markLine: o.reference ? { symbol: 'none', lineStyle: { color: css('--ds-critical'), type: 'dashed', width: 1.5 }, label: { show: false }, data: [{ xAxis: o.reference }] } : undefined }],
    };
  }

  function vbar(el, rows, o) {
    let data = o.sum_by_label ? sumBy(rows, o.label, o.value) : rows;
    data = sortRows(data, o.sort || ('-' + o.value));
    if (o.limit) data = data.slice(0, o.limit);
    return {
      ...base(), tooltip: tip(), grid: { left: 8, right: 12, top: 24, bottom: 8, containLabel: true },
      xAxis: axisCat(data.map((r) => fmt.label(r[o.label])), { axisLabel: { color: css('--ds-muted'), fontSize: fs(12), interval: 0, margin: 10 } }), yAxis: axisVal(),
      series: [{ type: 'bar', data: data.map((r) => Number(r[o.value]) || 0), barWidth: '46%', itemStyle: { color: css('--ds-s1'), borderRadius: [4, 4, 0, 0] },
        label: { show: true, position: 'top', color: css('--ds-ink'), fontSize: fs(13), fontWeight: 600 } }],
    };
  }

  function line(el, rows, o) {
    const colours = SERIES();
    let xs, series = [];
    if (o.group) {  // long format: one series per group value
      xs = [...new Set(rows.map((r) => r[o.x]))].sort();
      const groups = [...new Set(rows.map((r) => r[o.group]))];
      groups.forEach((g, i) => {
        const byX = new Map(rows.filter((r) => r[o.group] === g).map((r) => [r[o.x], Number(r[o.value])]));
        series.push({ name: fmt.label(g), type: 'line', data: xs.map((x) => (byX.has(x) ? byX.get(x) : null)), symbol: o.markers === false ? 'none' : 'circle', symbolSize: fs(7), connectNulls: true,
          lineStyle: { width: 2.5, color: colours[i % 6] }, itemStyle: { color: colours[i % 6] } });
      });
    } else {  // wide format: named columns
      const sorted = sortRows(rows, o.x); xs = sorted.map((r) => r[o.x]);
      o.series.forEach(([col, name], i) => {
        series.push({ name, type: 'line', data: sorted.map((r) => (r[col] == null ? null : Number(r[col]))), symbol: o.markers === false ? 'none' : 'circle', symbolSize: fs(7), connectNulls: true,
          lineStyle: { width: 2.5, color: colours[i % 6] }, itemStyle: { color: colours[i % 6] }, areaStyle: o.area && i === 0 ? { color: colours[0], opacity: 0.08 } : undefined });
      });
      if (o.average_of) {
        const vals = sorted.map((r) => Number(r[o.average_of]) || 0); const avg = vals.reduce((a, b) => a + b, 0) / (vals.length || 1);
        series.push({ name: '12-month average', type: 'line', data: xs.map(() => Math.round(avg * 10) / 10), symbol: 'none', lineStyle: { width: 1.5, type: 'dashed', color: css('--ds-muted') }, tooltip: { show: false } });
      }
    }
    if (o.reference) {
      series[0].markLine = { symbol: 'none', lineStyle: { color: css('--ds-critical'), type: 'dashed', width: 1.5 }, label: { formatter: o.reference.label, color: css('--ds-critical'), fontSize: fs(12), position: 'insideEndTop' }, data: [{ yAxis: o.reference.value }] };
    }
    const legend = series.filter((s) => !s.tooltip).length > 1 ? { bottom: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 12, textStyle: { color: css('--ds-ink-2'), fontSize: fs(12) } } : undefined;
    return { ...base(), tooltip: tip(), legend, grid: { left: 8, right: 16, top: 16, bottom: legend ? (series.length > 4 ? 50 : 28) : 8, containLabel: true },
      xAxis: axisCat(xs.map((x) => (o.x_format === 'month' ? fmt.month(x) : fmt.label(x)))), yAxis: axisVal({ max: o.max, min: o.min }), series };
  }

  function stacked(el, rows, o) {
    const colours = SERIES(); const horizontal = !!o.horizontal; let xs, series = [];
    if (o.group) {
      xs = o.x_format === 'month' ? [...new Set(rows.map((r) => r[o.x]))].sort() : [...new Set(rows.map((r) => r[o.x]))];
      const groups = [...new Set(rows.map((r) => r[o.group]))];
      const totals = new Map(); rows.forEach((r) => totals.set(r[o.x], (totals.get(r[o.x]) || 0) + Number(r[o.value] || 0)));
      groups.forEach((g, i) => {
        const byX = new Map(); rows.filter((r) => r[o.group] === g).forEach((r) => byX.set(r[o.x], (byX.get(r[o.x]) || 0) + Number(r[o.value] || 0)));
        series.push({ name: fmt.label(g), type: 'bar', stack: 'a', data: xs.map((x) => { const v = byX.get(x) || 0; return o.percent ? Math.round((v / (totals.get(x) || 1)) * 1000) / 10 : v; }), itemStyle: { color: colours[i % 6] }, barWidth: '50%' });
      });
    } else {
      const sorted = o.sum_by_x ? null : sortRows(rows, o.x);
      const data = sorted || [...new Set(rows.map((r) => r[o.x]))].map((x) => { const sub = rows.filter((r) => r[o.x] === x); const out = { [o.x]: x }; o.series.forEach(([c]) => (out[c] = sub.reduce((a, r) => a + Number(r[c] || 0), 0))); return out; });
      xs = data.map((r) => r[o.x]);
      o.series.forEach(([col, name], i) => series.push({ name, type: 'bar', stack: o.side_by_side ? undefined : 'a', data: data.map((r) => Number(r[col]) || 0), itemStyle: { color: colours[i % 6], borderRadius: o.side_by_side ? [3, 3, 0, 0] : 0 }, barWidth: o.side_by_side ? '30%' : '50%' }));
    }
    const cats = axisCat(xs.map((x) => (o.x_format === 'month' ? fmt.month(x) : fmt.label(x))), horizontal ? { axisLabel: { color: css('--ds-ink-2'), fontSize: fs(13) }, axisLine: { show: false } } : {});
    const vals = axisVal(o.percent ? { max: 100, axisLabel: { formatter: '{value} %', color: css('--ds-muted'), fontSize: fs(12) } } : {});
    return { ...base(), tooltip: tip(), legend: { bottom: 0, icon: 'roundRect', itemWidth: 12, itemHeight: 12, textStyle: { color: css('--ds-ink-2'), fontSize: fs(12) } },
      grid: { left: 8, right: 16, top: 12, bottom: 28, containLabel: true }, xAxis: horizontal ? vals : cats, yAxis: horizontal ? Object.assign(cats, { inverse: true }) : vals, series };
  }

  function status(el, rows, o) {  // DOM, not canvas
    el.classList.add('ds-status'); if (o.compact) el.classList.add('ds-status-compact');
    const items = [];
    if (o.single_row) {
      const r = rows[0] || {};
      o.items.forEach(([col, label, tone]) => items.push({ label, value: r[col], colour: css(STATUS[tone][0]) }));
    } else {
      const counts = new Map(); rows.forEach((r) => counts.set(r[o.key], (counts.get(r[o.key]) || 0) + 1));
      (o.order || [...counts.keys()]).forEach((k) => { if (!(k in STATUS)) return; items.push({ label: STATUS[k][1], value: counts.get(k) || 0, colour: css(STATUS[k][0]) }); });
    }
    el.innerHTML = items.map((i) => `<div><span class="ds-sw" style="background:${i.colour}"></span><span class="ds-status-label">${i.label}</span><b>${fmt.int(i.value)}</b></div>`).join('');
    return null;
  }

  function list(el, rows, o) {  // DOM, not canvas
    el.classList.add('ds-list');
    const sorted = rows.slice().sort((a, b) => (Number(b[o.pill]) || 0) - (Number(a[o.pill]) || 0));
    const data = (o.limit ? sorted.slice(0, o.limit) : sorted);
    el.innerHTML = data.length ? data.map((r) => {
      const v = Number(r[o.pill]) || 0; const tone = v >= (o.critical_at ?? Infinity) ? 'critical' : v >= (o.serious_at ?? Infinity) ? 'serious' : 'warn';
      const who = (o.who || []).map((k) => r[k]).filter(Boolean).join(' · ');
      return `<li><span class="ds-ref">${r[o.ref] ?? ''}</span><span class="ds-who" title="${who}">${who}</span><span class="ds-pill ds-pill-${tone}">${tone === 'critical' ? '⚠ ' : '● '}${fmt.int(v)} ${o.pill_unit || ''}</span></li>`;
    }).join('') : '<li class="ds-empty">Nothing waiting — the queue is clear.</li>';
    return null;
  }

  const IDIOMS = { hbar, vbar, line, stacked, status, list };

  // ---------------------------------------------------------------- KPI tiles
  function renderKpi(el, k, rows) {
    const r = rows[0] || {}; const f = fmt[k.fmt] || fmt.int;
    const v = r[k.value];
    let delta = '';
    if (k.delta && r[k.delta] != null) delta = `<div class="ds-delta ds-delta-flat">${fmt.int(r[k.delta])} ${k.delta_label || ''}</div>`;
    const link = (k.link && el.dataset.links === '1') ? `<a class="ds-tile-link" href="${k.link}">Open list →</a>` : '';
    el.innerHTML = `<h3>${k.title}</h3><div class="ds-v">${f(v)}${k.unit ? `<small>${k.unit}</small>` : ''}</div>${delta}${link}`;
  }

  // ---------------------------------------------------------------- page driver
  const charts = [];
  function disposeAll() { while (charts.length) { const c = charts.pop(); try { c.dispose(); } catch (e) { /* already gone */ } } }

  function renderDashboard(root, payload) {
    root.__payload = payload;  // kept so a theme toggle can re-render without a refetch
    disposeAll();
    root.querySelectorAll('[data-kpi]').forEach((el) => { const k = payload.kpis.find((x) => x.key === el.dataset.kpi); if (k) renderKpi(el, k, payload.data[k.view] || []); });
    root.querySelectorAll('[data-panel]').forEach((el) => {
      const p = payload.panels.find((x) => x.key === el.dataset.panel); if (!p) return;
      const rows = payload.data[p.view] || []; const fn = IDIOMS[p.kind]; if (!fn) return;
      el.innerHTML = ''; el.className = 'ds-chart';
      const option = fn(el, rows, p.options || {});
      if (option) { const c = echarts.init(el, null, { renderer: 'canvas' }); c.setOption(option); charts.push(c); }
    });
    const stamp = document.querySelector('[data-refreshed]');
    if (stamp) { const t = payload.refreshed_at ? new Date(payload.refreshed_at) : new Date(payload.generated_at); stamp.textContent = 'data refreshed ' + t.toLocaleTimeString('en-JM', { hour: '2-digit', minute: '2-digit' }); }
  }

  async function load(url) { const res = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } }); if (!res.ok) throw new Error('HTTP ' + res.status); return res.json(); }

  function buildGrid(root, payload) {  // used by the wall, which has no server-rendered panel shells
    root.innerHTML = `<section class="ds-kpis">${payload.kpis.map((k) => `<div class="ds-tile" data-kpi="${k.key}"></div>`).join('')}</section>
      <section class="ds-grid">${payload.panels.map((p) => `<div class="ds-card" style="grid-column:span ${p.span}"><h2>${p.title}</h2><p>${p.subtitle}</p><div class="ds-chart" data-panel="${p.key}"></div></div>`).join('')}</section>`;
  }

  window.WSDash = {
    async desk(root, url, refreshSeconds) {
      const run = async () => { try { renderDashboard(root, await load(url)); } catch (e) { root.querySelectorAll('[data-panel]').forEach((el) => (el.innerHTML = `<p class="ds-empty">Could not load data (${e.message}).</p>`)); } };
      await run();
      if (refreshSeconds) setInterval(run, refreshSeconds * 1000);  // live: re-fetch on the admin-set interval
    },
    wall(root, cfg) {
      let i = Math.max(0, cfg.order.indexOf(cfg.start)); let timer = null; let paused = false;
      const titleEl = document.querySelector('[data-wall-title]'); const noteEl = document.querySelector('[data-wall-note]'); const dots = document.querySelectorAll('[data-dot]');
      const counter = document.querySelector('[data-counter]'); const nextEl = document.querySelector('[data-next-title]'); const pauseBtn = document.querySelector('[data-pause]');
      async function show(idx) {
        i = (idx + cfg.order.length) % cfg.order.length; const slug = cfg.order[i];
        let payload; try { payload = await load(cfg.urls[slug] + '?wall=1'); } catch (e) { return; }
        titleEl.textContent = payload.title; noteEl.textContent = payload.source_note;
        counter.textContent = paused ? 'Rotation paused' : `Rotates every ${cfg.rotate} s · ${i + 1} / ${cfg.order.length}`;
        if (nextEl) nextEl.textContent = cfg.titles[cfg.order[(i + 1) % cfg.order.length]] || '';
        dots.forEach((d, j) => d.classList.toggle('on', j === i));
        buildGrid(root, payload); renderDashboard(root, payload);
      }
      function schedule() { clearInterval(timer); if (!paused) timer = setInterval(() => show(i + 1), cfg.rotate * 1000); }
      function go(idx) { show(idx); schedule(); }
      function togglePause() { paused = !paused; if (pauseBtn) { pauseBtn.classList.toggle('paused', paused); pauseBtn.textContent = paused ? '▶' : '⏸'; pauseBtn.title = paused ? 'Resume rotation (space)' : 'Pause rotation (space)'; } schedule(); show(i); }
      show(i); schedule();
      setInterval(() => show(i), cfg.refresh * 1000);  // re-fetch the current dashboard so new data appears without waiting for a rotation
      dots.forEach((d) => d.addEventListener('click', () => go(Number(d.dataset.dot))));
      const prev = document.querySelector('[data-prev]'), next = document.querySelector('[data-next]');
      if (prev) prev.addEventListener('click', () => go(i - 1)); if (next) next.addEventListener('click', () => go(i + 1)); if (pauseBtn) pauseBtn.addEventListener('click', togglePause);
      document.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowRight') go(i + 1); else if (e.key === 'ArrowLeft') go(i - 1); else if (e.key === ' ') { e.preventDefault(); togglePause(); } else if (e.key === 'Escape' && cfg.exit) location.href = cfg.exit;
      });
      const clock = document.querySelector('[data-clock]'), dateEl = document.querySelector('[data-date]');
      setInterval(() => { const n = new Date(); if (clock) clock.textContent = n.toLocaleTimeString('en-JM', { hour: '2-digit', minute: '2-digit' }); if (dateEl) dateEl.textContent = n.toLocaleDateString('en-JM', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }); }, 1000);
    },
  };

  window.addEventListener('resize', () => charts.forEach((c) => c.resize()));
  new MutationObserver(() => { const root = document.querySelector('[data-dashboard-root]'); if (root && root.__payload) renderDashboard(root, root.__payload); })
    .observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
})();
