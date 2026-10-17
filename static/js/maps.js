/* WaterSource map (v0.7.1): Leaflet; layers from /maps/layers/<name>.geojson; base-map switcher, labels, hover highlight,
   scale bar, fullscreen button, optional auto-refresh (TV page). Served with a CSP nonce — no inline script anywhere. */
(function () {
  "use strict";
  var el = document.getElementById("map");
  if (!el || typeof L === "undefined") return;
  var info = document.getElementById("map-info"), sources = document.getElementById("map-sources");
  var controls = document.getElementById("layer-controls");
  var defaults = (el.dataset.defaultLayers || "").split(",").filter(Boolean);
  var refresh = parseInt(el.dataset.refresh || "0", 10);
  var map = L.map(el, { zoomControl: true, zoomSnap: 0.25 }).setView([parseFloat(el.dataset.lat), parseFloat(el.dataset.lng)], parseInt(el.dataset.zoom, 10));

  // base maps -----------------------------------------------------------------------------
  var basemaps = {};
  (JSON.parse(el.dataset.basemaps || "[]")).forEach(function (b, i) {
    basemaps[b.name] = L.tileLayer(b.url, { attribution: b.attribution, maxZoom: 18 });
    if (i === 0) basemaps[b.name].addTo(map);
  });
  var overlays = {};
  if (el.dataset.hillshade) { overlays["Hillshade (relief)"] = L.tileLayer(el.dataset.hillshade, { opacity: 0.35, maxZoom: 16, attribution: "Hillshade &copy; Esri" }); }
  var switcher = L.control.layers(basemaps, overlays, { position: "topright", collapsed: true }).addTo(map);
  L.control.scale({ metric: true, imperial: false, position: "bottomleft" }).addTo(map);

  // fullscreen (browser Fullscreen API; the TV page is already edge to edge) ------------------
  var Full = L.Control.extend({
    onAdd: function () {
      var btn = L.DomUtil.create("a", "leaflet-bar ws-full-btn");
      btn.href = "#"; btn.title = "Full screen"; btn.textContent = "⛶"; btn.setAttribute("role", "button");
      L.DomEvent.on(btn, "click", function (e) {
        L.DomEvent.stop(e);
        if (document.fullscreenElement) { document.exitFullscreen(); }
        else if (el.requestFullscreen) { el.requestFullscreen(); }
        else if (el.dataset.fullUrl) { window.open(el.dataset.fullUrl, "_blank"); }
      });
      return btn;
    }
  });
  new Full({ position: "topleft" }).addTo(map);
  document.addEventListener("fullscreenchange", function () { setTimeout(function () { map.invalidateSize(); }, 150); });

  // styling ---------------------------------------------------------------------------------
  function colour(p) {
    var u = p.utilisation_with_pending_pct != null ? p.utilisation_with_pending_pct : p.utilisation_pct;
    if (p.safe_yield == null) return "#64748b";
    if (u > 100) return "#ef4444";
    if (u > 85) return "#f97316";
    if (u > 60) return "#eab308";
    return "#22c55e";
  }
  function fmt(n) { return n == null ? "—" : Number(n).toLocaleString("en-JM", { maximumFractionDigits: 0 }); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  var styles = {
    parishes: function () { return { color: "#cbd5e1", weight: 1.5, fill: false, dashArray: "5 4" }; },
    basins: function () { return { color: "#0ea5e9", weight: 3.5, fill: false }; },
    wmus: function (f) { return { color: "#0f172a", weight: 1, fillColor: colour(f.properties), fillOpacity: 0.4 }; },
    aquifers: function () { return { color: "#a855f7", weight: 2, dashArray: "2 4", fillColor: "#a855f7", fillOpacity: 0.18 }; },
    rivers: function () { return { color: "#2563eb", weight: 1.4, opacity: 0.9 }; },
    subwmus: function () { return { color: "#475569", weight: 0.8, dashArray: "3 3", fill: false }; },
    hydrostrat: function (f) { var c = hydroColour[f.properties.unit] || "#94a3b8"; return { color: c, weight: 0.6, fillColor: c, fillOpacity: 0.45 }; },
    floodplains: function () { return { color: "#4338ca", weight: 1, fillColor: "#6366f1", fillOpacity: 0.35 }; },
    melissa: function () { return { color: "#9f1239", weight: 0.8, fillColor: "#be123c", fillOpacity: 0.4 }; }
  };
  var hydroColour = { "Limestone Aquifer": "#0ea5e9", "Limestone Aquiclude": "#7dd3fc", "Alluvium Aquifer": "#f59e0b", "Alluvium Aquiclude": "#fde68a",
    "Coastal Aquifer": "#14b8a6", "Coastal Aquiclude": "#99f6e4", "Basal Aquiclude": "#a8a29e", "Swamp/Marsh/Mangrove": "#65a30d", "Water Body": "#1d4ed8" };
  var hover = { weight: 4, color: "#ffffff" };
  var popups = {
    parishes: function (p) { return "<strong>" + esc(p.name) + "</strong><br>Parish<br><span class='text-muted'>" + esc(p.source) + "</span>"; },
    basins: function (p) { return "<strong>" + esc(p.name) + "</strong><br>Hydrological basin · " + p.wmus + " WMU(s)<br><span class='text-muted'>" + esc(p.source) + "</span>"; },
    wmus: function (p) {
      return "<strong>" + esc(p.name) + "</strong> (" + esc(p.code) + ")<br>Basin: " + esc(p.basin) +
        "<br>Safe yield: " + fmt(p.safe_yield) + " m³/day<br>Licensed: " + fmt(p.allocated) + " m³/day (" + p.licences + " licence(s))" +
        "<br>Pending: " + fmt(p.pending) + " m³/day<br>Utilisation: " + (p.utilisation_pct == null ? "—" : p.utilisation_pct + " %") +
        (p.utilisation_with_pending_pct != null ? " · with pending " + p.utilisation_with_pending_pct + " %" : "") +
        "<br><span class='text-muted'>" + esc(p.source) + "</span>";
    },
    aquifers: function (p) { return "<strong>" + esc(p.name) + "</strong><br>" + esc(p.type) + " aquifer · " + esc(p.basin) + "<br>Safe yield: " + fmt(p.safe_yield_m3_d) + " m³/day<br><span class='text-muted'>" + esc(p.source) + "</span>"; },
    rivers: function (p) { return "<strong>" + esc(p.name || "Unnamed waterway") + "</strong><br>River / waterway<br><span class='text-muted'>" + esc(p.source) + "</span>"; },
    subwmus: function (p) { return "<strong>" + esc(p.name || "Sub-WMU") + "</strong><br>Sub-WMU<br><span class='text-muted'>" + esc(p.source) + "</span>"; },
    hydrostrat: function (p) { return "<strong>" + esc(p.unit) + "</strong><br>Hydrostratigraphy 2018<br><span class='text-muted'>" + esc(p.source) + "</span>"; },
    floodplains: function (p) { return "<strong>" + esc(p.study) + "</strong><br>" + esc(p.rp || "100 yr") + " floodplain (WRA flood study)" + (p.area_km2 ? "<br>Area: " + Number(p.area_km2).toFixed(2) + " km²" : "") + "<br><span class='text-muted'>" + esc(p.source) + "</span>"; },
    melissa: function (p) { return "<strong>" + esc(p.name || "Flooded area") + "</strong><br>Hurricane Melissa flooding" + (p.flood_type ? " · " + esc(p.flood_type) : "") + "<br>" + esc(p.parish || "") + (p.wmu ? " · " + esc(p.wmu) : "") + (p.captured ? "<br>Captured: " + esc(p.captured) : "") + (p.area_km2 ? "<br>Area: " + Number(p.area_km2).toFixed(2) + " km²" : "") + (p.remarks ? "<br><em>" + esc(p.remarks) + "</em>" : "") + "<br><span class='text-muted'>" + esc(p.source) + "</span>"; },
    gauges: function (p) {
      return "<strong>" + esc(p.name || p.code) + "</strong> (" + esc(p.code) + ")<br>WRA gauging station" + (p.type ? " · " + esc(p.type) : "") + (p.state ? " · " + esc(p.state) : "") +
        "<br>" + esc(p.wmu || "") + (p.basin ? " · " + esc(p.basin) : "") + (p.drainage_km2 ? "<br>Drainage area: " + fmt(p.drainage_km2) + " km²" : "") +
        (p.elevation_m ? " · " + fmt(p.elevation_m) + " m" : "") + "<br><span class='text-muted'>" + esc(p.source) + "</span>";
    },
    sites: function (p) {
      var kind = { well: "Well", station: "Streamflow station", spring: "Spring" }[p.kind] || p.kind;
      return "<strong>" + esc(p.name) + "</strong><br>" + kind + (p.use ? " · " + esc(p.use) : "") + (p.river ? " · " + esc(p.river) : "") +
        "<br>" + esc(p.parish || "") + (p.wmu ? " · " + esc(p.wmu) : "") +
        (p.public_supply ? "<br><em>Public supply" + (p.coordinates_coarsened ? " — position coarsened" : "") + "</em>" : "");
    }
  };
  var markerStyle = { well: { radius: 6, color: "#1d4ed8", fillColor: "#3b82f6" }, station: { radius: 7, color: "#047857", fillColor: "#10b981" }, spring: { radius: 6, color: "#b45309", fillColor: "#f59e0b" } };
  var labelLayers = { parishes: "ws-label-parish", basins: "ws-label-basin", wmus: "ws-label-wmu" };
  var labelMinZoom = { parishes: 9.5, basins: 0, wmus: 10 }; // avoid a pile-up of names when the whole island is in view
  var names = { parishes: "Parishes", basins: "Basins", wmus: "Water management units", aquifers: "Aquifers", sites: "Wells, stations and springs",
    hydrostrat: "Hydrostratigraphy (WRA 2018)", subwmus: "Sub-WMUs", rivers: "Rivers (WRA)", gauges: "Gauging stations (WRA)",
    floodplains: "100-year floodplains (WRA studies)", melissa: "Hurricane Melissa flooded areas (WRA)" };
  var order = ["hydrostrat", "aquifers", "wmus", "subwmus", "floodplains", "melissa", "parishes", "basins", "rivers", "gauges", "sites"]; // draw order, bottom to top
  var pointLayers = { sites: true, gauges: true };

  // layers ---------------------------------------------------------------------------------
  var layers = {}, data = {}, labelsOn = defaults.indexOf("labels") >= 0, labels = L.layerGroup();
  var seen = {}, fitted = false;
  function restack() { order.forEach(function (n) { if (layers[n] && map.hasLayer(layers[n])) { try { layers[n].bringToFront(); } catch (e) { /* point layers */ } } }); }
  function labelFor(name, f) {
    if (!labelLayers[name] || !f.properties.name) return null;
    if (name === "wmus" && layers.basins && map.hasLayer(layers.basins) && f.properties.basin === f.properties.name) return null;
    var c = L.geoJSON(f).getBounds().getCenter();
    return L.marker(c, { interactive: false, icon: L.divIcon({ className: "ws-label " + labelLayers[name], html: esc(f.properties.name), iconSize: null }) });
  }
  function rebuildLabels() {
    labels.clearLayers();
    if (!labelsOn) return;
    var z = map.getZoom();
    Object.keys(data).forEach(function (name) {
      if (!layers[name] || !map.hasLayer(layers[name]) || z < (labelMinZoom[name] || 0)) return;
      data[name].features.forEach(function (f) { var m = labelFor(name, f); if (m) labels.addLayer(m); });
    });
    labels.addTo(map);
  }
  function build(name, gj) {
    data[name] = gj;
    var opts = {
      onEachFeature: function (f, l) {
        l.bindPopup(popups[name](f.properties));
        l.on("click", function () { if (info) info.innerHTML = popups[name](f.properties); if (name === "wmus") openWmu(f.properties.code); });
        if (!pointLayers[name]) {
          l.on("mouseover", function () { l.setStyle(hover); l.bringToFront(); });
          l.on("mouseout", function () { layers[name].resetStyle(l); restack(); });
          l.bindTooltip(f.properties.name, { sticky: true, className: "ws-tip" });
        } else {
          l.bindTooltip(f.properties.name, { direction: "top", offset: [0, -6], className: "ws-tip" });
        }
      }
    };
    if (name === "sites") {
      opts.pointToLayer = function (f, latlng) { var s = markerStyle[f.properties.kind] || markerStyle.well; return L.circleMarker(latlng, Object.assign({ weight: 2, fillOpacity: 0.95 }, s)); };
    } else if (name === "gauges") {
      opts.pointToLayer = function (f, latlng) { return L.marker(latlng, { icon: L.divIcon({ className: "ws-gauge-wrap", html: "<span class='ws-gauge'></span>", iconSize: [10, 10], iconAnchor: [5, 5] }) }); };
    } else { opts.style = styles[name]; }
    if (layers[name]) { switcher.removeLayer(layers[name]); map.removeLayer(layers[name]); }
    layers[name] = L.geoJSON(gj, opts);
    switcher.addOverlay(layers[name], names[name]);
    (gj.sources || []).forEach(function (s) { seen[s] = true; });
    if (sources) sources.textContent = Object.keys(seen).length ? "Boundary sources: " + Object.keys(seen).join(" · ") : "";
  }
  function show(name) {
    if (layers[name]) { layers[name].addTo(map); restack(); rebuildLabels(); return; }
    fetch(el.dataset.layerUrl.replace("LAYER", name), { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (gj) {
      build(name, gj); layers[name].addTo(map); restack(); rebuildLabels();
      if (!fitted && name === "parishes" && gj.features.length) { map.fitBounds(layers[name].getBounds(), { padding: [10, 10] }); fitted = true; }
      var cb = controls && controls.querySelector('input[data-layer="' + name + '"]'); if (cb) cb.checked = true;
    }).catch(function () { if (info) info.textContent = "Could not load the " + name + " layer."; });
  }
  function hide(name) { if (layers[name]) map.removeLayer(layers[name]); rebuildLabels(); }

  // panel checkboxes mirror the on-map switcher and vice versa
  if (controls) {
    controls.querySelectorAll("input[data-layer]").forEach(function (cb) {
      var name = cb.dataset.layer;
      if (name === "labels") { cb.checked = labelsOn; cb.addEventListener("change", function () { labelsOn = cb.checked; rebuildLabels(); }); return; }
      cb.checked = defaults.indexOf(name) >= 0;
      cb.addEventListener("change", function () { if (cb.checked) show(name); else hide(name); });
    });
  }
  map.on("zoomend", rebuildLabels);
  map.on("overlayadd overlayremove", function (e) {
    var name = Object.keys(layers).find(function (n) { return layers[n] === e.layer; });
    var cb = controls && name && controls.querySelector('input[data-layer="' + name + '"]');
    if (cb) cb.checked = e.type === "overlayadd";
    restack(); rebuildLabels();
  });
  // ---- v0.12.0: shareable link (#map=zoom/lat/lng&layers=a,b&base=Name) ----------------------------------------------
  var hashState = {};
  (location.hash || "").replace(/^#/, "").split("&").forEach(function (kv) { var i = kv.indexOf("="); if (i > 0) hashState[kv.slice(0, i)] = decodeURIComponent(kv.slice(i + 1)); });
  if (hashState.layers !== undefined) { defaults = hashState.layers.split(",").filter(Boolean); labelsOn = defaults.indexOf("labels") >= 0; if (controls) controls.querySelectorAll("input[data-layer]").forEach(function (cb) { cb.checked = defaults.indexOf(cb.dataset.layer) >= 0; }); }
  if (hashState.base && basemaps[hashState.base]) { Object.keys(basemaps).forEach(function (k) { if (map.hasLayer(basemaps[k])) map.removeLayer(basemaps[k]); }); basemaps[hashState.base].addTo(map); }
  if (hashState.map) { var m = hashState.map.split("/").map(Number); if (m.length === 3 && m.every(isFinite)) { map.setView([m[1], m[2]], m[0]); fitted = true; } }
  function currentBase() { return Object.keys(basemaps).find(function (k) { return map.hasLayer(basemaps[k]); }) || ""; }
  function stateHash() {
    var c = map.getCenter(), on = order.filter(function (n) { return layers[n] && map.hasLayer(layers[n]); });
    if (labelsOn) on.push("labels");
    return "#map=" + map.getZoom() + "/" + c.lat.toFixed(4) + "/" + c.lng.toFixed(4) + "&layers=" + on.join(",") + "&base=" + encodeURIComponent(currentBase());
  }
  function writeHash() { try { history.replaceState(null, "", location.pathname + location.search + stateHash()); } catch (e) { /* ignore */ } }
  map.on("moveend zoomend overlayadd overlayremove baselayerchange", writeHash);
  var share = document.getElementById("map-share"), shareMsg = document.getElementById("map-share-msg");
  if (share) {
    share.addEventListener("click", function () {
      writeHash();
      var url = location.href, done = function () { if (shareMsg) { shareMsg.textContent = "Link copied — it opens the map at this view with these layers."; setTimeout(function () { shareMsg.textContent = ""; }, 4000); } };
      if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(url).then(done, function () { window.prompt("Copy this link:", url); }); } else { window.prompt("Copy this link:", url); }
    });
  }

  // ---- v0.12.0: find on the map ----------------------------------------------------------------------------------------
  var search = document.getElementById("map-search"), results = document.getElementById("map-search-results");
  var kinds = { wmus: "WMU", basins: "Basin", parishes: "Parish", subwmus: "Sub-WMU", gauges: "Gauging station", rivers: "River", aquifers: "Aquifer" };
  function searchIndex() {
    var out = [];
    Object.keys(data).forEach(function (name) {
      (data[name].features || []).forEach(function (f) {
        var p = f.properties, label = p.name; if (!label) return;
        var kind = name === "sites" ? ({ well: "Well", station: "Streamflow station", spring: "Spring" }[p.kind] || p.kind) : (kinds[name] || name);
        out.push({ label: label, kind: kind, layer: name, feature: f, extra: p.code || p.parish || p.basin || "" });
      });
    });
    return out;
  }
  var active = -1, hits = [];
  function render(list) {
    if (!results) return;
    results.innerHTML = ""; hits = list.slice(0, 12); active = -1;
    hits.forEach(function (h, i) { var li = document.createElement("li"); li.innerHTML = esc(h.label) + "<span class='kind'>" + esc(h.kind) + (h.extra ? " · " + esc(h.extra) : "") + "</span>"; li.addEventListener("mousedown", function (e) { e.preventDefault(); go(i); }); results.appendChild(li); });
    results.hidden = hits.length === 0;
  }
  function go(i) {
    var h = hits[i]; if (!h) return;
    results.hidden = true; search.value = h.label;
    var lyr = L.geoJSON(h.feature), b = lyr.getBounds();
    if (h.feature.geometry.type === "Point") { map.setView(b.getCenter(), Math.max(map.getZoom(), 13)); } else { map.fitBounds(b, { padding: [20, 20] }); }
    if (!layers[h.layer] || !map.hasLayer(layers[h.layer])) show(h.layer);
    setTimeout(function () {
      var target = null;
      if (layers[h.layer]) layers[h.layer].eachLayer(function (l) { if (l.feature === h.feature) target = l; });
      if (target) { if (target.openPopup) target.openPopup(); if (info) info.innerHTML = popups[h.layer](h.feature.properties); if (h.layer === "wmus") openWmu(h.feature.properties.code); }
    }, 350);
  }
  if (search) {
    search.addEventListener("input", function () {
      var q = search.value.trim().toLowerCase();
      if (q.length < 2) { render([]); return; }
      var idx = searchIndex();
      var starts = idx.filter(function (h) { return h.label.toLowerCase().indexOf(q) === 0; }), contains = idx.filter(function (h) { return h.label.toLowerCase().indexOf(q) > 0; });
      render(starts.concat(contains));
    });
    search.addEventListener("keydown", function (e) {
      if (results.hidden) return;
      var items = results.querySelectorAll("li");
      if (e.key === "ArrowDown") { active = Math.min(active + 1, items.length - 1); } else if (e.key === "ArrowUp") { active = Math.max(active - 1, 0); } else if (e.key === "Enter") { e.preventDefault(); go(active < 0 ? 0 : active); return; } else if (e.key === "Escape") { results.hidden = true; return; } else { return; }
      e.preventDefault(); items.forEach(function (li, i) { li.classList.toggle("is-active", i === active); });
    });
    search.addEventListener("blur", function () { setTimeout(function () { results.hidden = true; }, 150); });
  }

  // ---- v0.12.0: WMU panel ---------------------------------------------------------------------------------------------
  var panel = document.getElementById("map-panel");
  function spark(series) {
    if (!series || series.length < 2) return "<p class='text-muted mt-2 text-xs'>No approved abstraction returns in the last 12 months.</p>";
    var w = 260, h = 56, max = Math.max.apply(null, series.map(function (d) { return d.m3; })) || 1, n = series.length;
    var pts = series.map(function (d, i) { return [(i / (n - 1)) * (w - 4) + 2, h - 4 - (d.m3 / max) * (h - 10)]; });
    var path = pts.map(function (p, i) { return (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); }).join(" ");
    var area = path + " L" + pts[n - 1][0].toFixed(1) + " " + (h - 2) + " L" + pts[0][0].toFixed(1) + " " + (h - 2) + " Z";
    return "<svg class='map-spark' viewBox='0 0 " + w + " " + h + "' preserveAspectRatio='none' role='img' aria-label='Reported abstraction by month'>" +
      "<path d='" + area + "' fill='#3a8ff0' fill-opacity='.18'/><path d='" + path + "' fill='none' stroke='#2470e0' stroke-width='2'/></svg>" +
      "<p class='text-muted text-xs'>Reported abstraction by month, " + esc(series[0].month) + " to " + esc(series[n - 1].month) + " · peak " + fmt(max) + " m³</p>";
  }
  function openWmu(code) {
    if (!panel || !el.dataset.wmuUrl) return;
    panel.hidden = false; panel.innerHTML = "<p class='text-muted'>Loading " + esc(code) + "…</p>";
    fetch(el.dataset.wmuUrl.replace("CODE", code), { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (d) {
      var u = d.utilisation_with_pending_pct != null ? d.utilisation_with_pending_pct : d.utilisation_pct;
      var colourOf = colour({ safe_yield: d.safe_yield, utilisation_pct: d.utilisation_pct, utilisation_with_pending_pct: d.utilisation_with_pending_pct });
      var html = "<button type='button' class='close' aria-label='Close'>×</button><h3>" + esc(d.name) + " <span class='text-muted text-xs'>" + esc(d.code) + "</span></h3>" +
        "<p class='text-muted text-xs'>" + esc(d.basin || "") + (d.subwmus && d.subwmus.length ? " · sub-WMUs: " + esc(d.subwmus.join(", ")) : "") + "</p>" +
        "<div class='map-bar' title='Utilisation of safe yield'><span style='width:" + Math.min(100, u || 0) + "%;background:" + colourOf + "'></span></div>" +
        "<p class='text-xs mt-1'>" + (u == null ? "No safe yield set" : u + " % of safe yield" + (d.pending ? " including pending" : "")) + "</p>" +
        "<dl><dt>Safe yield</dt><dd>" + fmt(d.safe_yield) + " m³/d</dd><dt>Licensed</dt><dd>" + fmt(d.allocated) + " m³/d</dd><dt>Pending</dt><dd>" + fmt(d.pending) + " m³/d</dd><dt>Headroom</dt><dd>" + fmt(d.headroom) + " m³/d</dd>" +
        "<dt>Reported (12 mo avg)</dt><dd>" + fmt(d.reported_avg) + " m³/d</dd><dt>Active licences</dt><dd>" + d.licences + "</dd><dt>Wells · stations</dt><dd>" + d.wells + " · " + d.stations + (d.gauges ? " (+" + d.gauges + " WRA gauges)" : "") + "</dd></dl>" +
        spark(d.abstraction_monthly) +
        (d.licence_list && d.licence_list.length ? "<p class='mt-2 text-xs font-semibold'>Largest active licences</p><ul class='lics'>" + d.licence_list.map(function (l) { return "<li><a class='link' href='" + esc(l.url) + "'>" + esc(l.number) + "</a> · " + fmt(l.volume) + " m³/d" + (l.expires ? " · to " + esc(l.expires) : "") + "</li>"; }).join("") + "</ul>" : "") +
        "<p class='mt-2 text-xs'><a class='link' href='/licensing/balance/'>WMU balance sheet →</a>" + (d.safe_yield_source ? "<br><span class='text-muted'>Safe yield: " + esc(d.safe_yield_source) + "</span>" : "") + "</p>";
      panel.innerHTML = html;
      panel.querySelector(".close").addEventListener("click", function () { panel.hidden = true; });
    }).catch(function () { panel.innerHTML = "<p class='text-danger'>Could not load this WMU.</p>"; });
  }

  // initial layers: parishes first so the map fits the island, then the rest in draw order
  ["parishes"].concat(order.filter(function (n) { return n !== "parishes"; })).forEach(function (n) { if (defaults.indexOf(n) >= 0) show(n); });

  // TV page: re-fetch visible layers so utilisation colours stay current
  if (refresh > 0) {
    setInterval(function () {
      Object.keys(layers).forEach(function (name) {
        if (!map.hasLayer(layers[name])) return;
        fetch(el.dataset.layerUrl.replace("LAYER", name), { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (gj) { build(name, gj); layers[name].addTo(map); restack(); rebuildLabels(); });
      });
    }, refresh * 1000);
  }
})();
