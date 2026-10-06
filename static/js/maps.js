/* WaterSource map (v0.7.0): Leaflet, layers from /maps/layers/<name>.geojson. No inline script (CSP nonce on the tag). */
(function () {
  "use strict";
  var el = document.getElementById("map");
  if (!el || typeof L === "undefined") return;
  var map = L.map(el, { zoomControl: true }).setView([parseFloat(el.dataset.lat), parseFloat(el.dataset.lng)], parseInt(el.dataset.zoom, 10));
  L.tileLayer(el.dataset.tiles, { attribution: el.dataset.attribution, maxZoom: 18 }).addTo(map);
  var urlFor = function (name) { return el.dataset.layerUrl.replace("LAYER", name); };
  var info = document.getElementById("map-info"), sources = document.getElementById("map-sources");
  var seen = {};

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
    parishes: function () { return { color: "#94a3b8", weight: 1.2, fill: false, dashArray: "4 3" }; },
    basins: function () { return { color: "#0ea5e9", weight: 2, fillColor: "#0ea5e9", fillOpacity: 0.06 }; },
    wmus: function (f) { return { color: "#0f172a", weight: 1, fillColor: colour(f.properties), fillOpacity: 0.35 }; },
    aquifers: function () { return { color: "#a855f7", weight: 1.5, fillColor: "#a855f7", fillOpacity: 0.12 }; }
  };
  var popups = {
    parishes: function (p) { return "<strong>" + esc(p.name) + "</strong><br>Parish · " + esc(p.source); },
    basins: function (p) { return "<strong>" + esc(p.name) + "</strong><br>Basin · " + p.wmus + " WMU(s)<br><span class='text-muted'>" + esc(p.source) + "</span>"; },
    wmus: function (p) {
      return "<strong>" + esc(p.name) + "</strong> (" + esc(p.code) + ")<br>Basin: " + esc(p.basin) +
        "<br>Safe yield: " + fmt(p.safe_yield) + " m³/day<br>Licensed: " + fmt(p.allocated) + " m³/day (" + p.licences + " licence(s))" +
        "<br>Pending: " + fmt(p.pending) + " m³/day<br>Utilisation: " + (p.utilisation_pct == null ? "—" : p.utilisation_pct + " %") +
        (p.utilisation_with_pending_pct != null ? " · with pending " + p.utilisation_with_pending_pct + " %" : "") +
        "<br><span class='text-muted'>" + esc(p.source) + "</span>";
    },
    aquifers: function (p) { return "<strong>" + esc(p.name) + "</strong><br>" + esc(p.type) + " aquifer · " + esc(p.basin) + "<br>Safe yield: " + fmt(p.safe_yield_m3_d) + " m³/day"; },
    sites: function (p) {
      var kind = { well: "Well", station: "Streamflow station", spring: "Spring" }[p.kind] || p.kind;
      return "<strong>" + esc(p.name) + "</strong><br>" + kind + (p.use ? " · " + esc(p.use) : "") + (p.river ? " · " + esc(p.river) : "") +
        "<br>" + esc(p.parish || "") + (p.wmu ? " · " + esc(p.wmu) : "") +
        (p.public_supply ? "<br><em>Public supply" + (p.coordinates_coarsened ? " — position coarsened" : "") + "</em>" : "");
    }
  };
  var markerStyle = { well: { radius: 5, color: "#1d4ed8", fillColor: "#3b82f6" }, station: { radius: 6, color: "#047857", fillColor: "#10b981" }, spring: { radius: 5, color: "#b45309", fillColor: "#f59e0b" } };

  var layers = {};
  function load(name) {
    if (layers[name]) { layers[name].addTo(map); return; }
    fetch(urlFor(name), { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (gj) {
      var opts = { onEachFeature: function (f, l) { l.bindPopup(popups[name](f.properties)); l.on("click", function () { info.innerHTML = popups[name](f.properties); }); } };
      if (name === "sites") {
        opts.pointToLayer = function (f, latlng) { var s = markerStyle[f.properties.kind] || markerStyle.well; return L.circleMarker(latlng, Object.assign({ weight: 1.5, fillOpacity: 0.9 }, s)); };
      } else { opts.style = styles[name]; }
      layers[name] = L.geoJSON(gj, opts).addTo(map);
      (gj.sources || []).forEach(function (s) { seen[s] = true; });
      sources.textContent = Object.keys(seen).length ? "Boundary sources: " + Object.keys(seen).join(" · ") : "";
    }).catch(function () { info.textContent = "Could not load the " + name + " layer."; });
  }
  document.querySelectorAll("#layer-controls input[data-layer]").forEach(function (cb) {
    cb.addEventListener("change", function () { if (cb.checked) load(cb.dataset.layer); else if (layers[cb.dataset.layer]) map.removeLayer(layers[cb.dataset.layer]); });
    if (cb.checked) load(cb.dataset.layer);
  });
})();
