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
    aquifers: function () { return { color: "#a855f7", weight: 2, dashArray: "2 4", fillColor: "#a855f7", fillOpacity: 0.18 }; }
  };
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
  var names = { parishes: "Parishes", basins: "Basins", wmus: "Water management units", aquifers: "Aquifers", sites: "Wells, stations and springs" };
  var order = ["aquifers", "wmus", "parishes", "basins", "sites"]; // draw order, bottom to top

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
        l.on("click", function () { if (info) info.innerHTML = popups[name](f.properties); });
        if (name !== "sites") {
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
