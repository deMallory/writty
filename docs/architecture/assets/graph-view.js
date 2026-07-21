/* Interactive force-directed view of the live knowledge-graph snapshot
   (assets/graph-data.js). Canvas + d3-force; pan/zoom; click to inspect. */

(function () {
  var DATA = window.WRIT_GRAPH;
  if (!DATA || !window.d3) return;

  var DECLARED = [
    "DEPENDS_ON", "PRECEDES", "CONFLICTS_WITH", "SUPPLEMENTS", "SUPERSEDES",
    "TEACHES", "COUNTERS", "DEMONSTRATES", "DISPATCHES", "GATES",
    "PRESSURE_TESTS", "CONTAINS", "ATTACHED_TO", "INVOKES",
  ];
  var PRESETS = {
    skeleton: { label: "Curated skeleton", types: DECLARED },
    related: { label: "+ cross-references", types: DECLARED.concat(["RELATED_TO"]) },
    abstracts: { label: "+ abstractions", types: DECLARED.concat(["RELATED_TO", "ABSTRACTS"]) },
    everything: { label: "Everything", types: DECLARED.concat(["RELATED_TO", "ABSTRACTS", "BELONGS_TO"]) },
  };
  var TYPE_COLORS = {
    Rule: "#0B5E55", Skill: "#1D6FB8", Playbook: "#B4560F", Technique: "#2E8540",
    AntiPattern: "#C03546", ForbiddenResponse: "#7A1F3D", Phase: "#5A6C70",
    Rationalization: "#9A7B2D", PressureScenario: "#A85B8A", WorkedExample: "#4B8E8D",
    SubagentRole: "#6B4FA0", Category: "#C2452D", Abstraction: "#8A6FC8", Project: "#444444",
  };
  var EDGE_COLORS = { RELATED_TO: "#AFC2BB", BELONGS_TO: "#DFC49E", ABSTRACTS: "#C9B8E8" };
  var DECLARED_EDGE_COLOR = "#0B4A42";
  var HIT_RADIUS = 14;
  var CLICK_SLOP_PX = 5;
  var LABEL_ZOOM_ALL = 2.4;
  var TOP_LABEL_COUNT = 20;
  /* Translucent strokes stack: at 2x the derived-edge count, a 0.35 wash reads
     like 0.7 and the hand-authored overlay loses contrast. Scale alpha down as
     density grows so total derived ink stays near what 0.35 gives at the 1,091
     derived edges this was tuned on. */
  var DERIVED_ALPHA_BASE = 0.35;
  var DERIVED_INK_REF = 1100;

  var canvas = document.getElementById("graph-canvas");
  var wrap = canvas.parentElement;
  var tip = document.getElementById("graph-tip");
  var stats = document.getElementById("graph-stats");
  var aside = document.getElementById("graph-aside");
  var searchBox = document.getElementById("graph-search");
  var ctx = canvas.getContext("2d");

  var nodeById = new Map();
  DATA.nodes.forEach(function (n) { nodeById.set(n.id, n); });

  /* full-graph degree per node (used for the always-on labels) */
  var fullDegree = new Map();
  DATA.edges.forEach(function (e) {
    fullDegree.set(e.source, (fullDegree.get(e.source) || 0) + 1);
    fullDegree.set(e.target, (fullDegree.get(e.target) || 0) + 1);
  });

  var state = {
    preset: "everything",
    hideIsolated: true,
    nodes: [],
    links: [],
    degree: new Map(),
    selected: null,
    hovered: null,
    transform: d3.zoomIdentity,
  };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null && text !== "") node.textContent = text;
    return node;
  }

  function rebuild() {
    var allowed = new Set(PRESETS[state.preset].types);
    var links = DATA.edges
      .filter(function (e) { return allowed.has(e.type); })
      .map(function (e) { return { source: e.source, target: e.target, type: e.type }; });

    var degree = new Map();
    links.forEach(function (l) {
      degree.set(l.source, (degree.get(l.source) || 0) + 1);
      degree.set(l.target, (degree.get(l.target) || 0) + 1);
    });

    var nodes = DATA.nodes.filter(function (n) {
      if (state.hideIsolated && !degree.get(n.id)) return false;
      return true;
    });
    var kept = new Set(nodes.map(function (n) { return n.id; }));
    links = links.filter(function (l) { return kept.has(l.source) && kept.has(l.target); });

    /* keep positions across preset switches so the layout feels continuous */
    var prev = new Map(state.nodes.map(function (n) { return [n.id, n]; }));
    nodes = nodes.map(function (n) {
      var p = prev.get(n.id);
      return p ? Object.assign(p, n) : Object.assign({}, n);
    });

    state.nodes = nodes;
    state.links = links;
    state.degree = degree;
    var derivedCount = links.reduce(function (c, l) { return c + (EDGE_COLORS[l.type] ? 1 : 0); }, 0);
    state.derivedAlpha = derivedCount > DERIVED_INK_REF
      ? DERIVED_ALPHA_BASE * (DERIVED_INK_REF / derivedCount)
      : DERIVED_ALPHA_BASE;
    if (state.selected && !kept.has(state.selected.id)) state.selected = null;

    sim.nodes(nodes);
    sim.force("link").links(links);
    sim.alpha(0.9).restart();

    stats.textContent = nodes.length + " nodes, " + links.length + " edges shown (of "
      + DATA.nodes.length + " / " + DATA.edges.length + ")";
    renderAside();
  }

  var sim = d3.forceSimulation()
    .force("link", d3.forceLink().id(function (d) { return d.id; })
      .distance(function (l) { return l.type === "BELONGS_TO" ? 75 : 42; })
      .strength(0.5))
    .force("charge", d3.forceManyBody().strength(-65))
    .force("center", d3.forceCenter(0, 0))
    .force("x", d3.forceX(0).strength(0.045))
    .force("y", d3.forceY(0).strength(0.045))
    .force("collide", d3.forceCollide().radius(function (d) { return radiusOf(d) + 2; }))
    .on("tick", draw);

  function radiusOf(n) {
    var deg = state.degree.get(n.id) || 0;
    return Math.min(3 + Math.sqrt(deg) * 1.7, 16);
  }

  function resize() {
    var dpr = window.devicePixelRatio || 1;
    canvas.width = wrap.clientWidth * dpr;
    canvas.height = wrap.clientHeight * dpr;
    draw();
  }

  function draw() {
    var dpr = window.devicePixelRatio || 1;
    var w = canvas.width / dpr;
    var h = canvas.height / dpr;
    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.translate(w / 2 + state.transform.x, h / 2 + state.transform.y);
    ctx.scale(state.transform.k, state.transform.k);

    var k = state.transform.k;
    var selected = state.selected;
    var neighborIds = null;
    if (selected) {
      neighborIds = new Set([selected.id]);
      state.links.forEach(function (l) {
        if (l.source.id === selected.id) neighborIds.add(l.target.id);
        if (l.target.id === selected.id) neighborIds.add(l.source.id);
      });
    }

    /* two passes: derived layers underneath, the scarce hand-authored edges
       on top at full strength so they never drown in the derived wash */
    ctx.lineWidth = 1 / k;
    state.links.forEach(function (l) {
      if (!EDGE_COLORS[l.type]) return;
      var dim = neighborIds && !(neighborIds.has(l.source.id) && neighborIds.has(l.target.id));
      ctx.strokeStyle = EDGE_COLORS[l.type];
      ctx.globalAlpha = dim ? 0.06 : state.derivedAlpha;
      ctx.beginPath();
      ctx.moveTo(l.source.x, l.source.y);
      ctx.lineTo(l.target.x, l.target.y);
      ctx.stroke();
    });
    ctx.lineWidth = 1.6 / k;
    state.links.forEach(function (l) {
      if (EDGE_COLORS[l.type]) return;
      var dim = neighborIds && !(neighborIds.has(l.source.id) && neighborIds.has(l.target.id));
      ctx.strokeStyle = DECLARED_EDGE_COLOR;
      ctx.globalAlpha = dim ? 0.08 : 0.9;
      ctx.beginPath();
      ctx.moveTo(l.source.x, l.source.y);
      ctx.lineTo(l.target.x, l.target.y);
      ctx.stroke();
    });

    /* top-degree nodes get labels at any zoom; everything gets one zoomed in */
    var labeled = state.nodes
      .slice()
      .sort(function (a, b) { return (fullDegree.get(b.id) || 0) - (fullDegree.get(a.id) || 0); })
      .slice(0, TOP_LABEL_COUNT);
    var labelSet = new Set(labeled.map(function (n) { return n.id; }));

    state.nodes.forEach(function (n) {
      var r = radiusOf(n);
      var dim = neighborIds && !neighborIds.has(n.id);
      ctx.globalAlpha = dim ? 0.15 : 1;
      ctx.fillStyle = TYPE_COLORS[n.type] || "#888888";
      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, 2 * Math.PI);
      ctx.fill();
      if (n === state.hovered || n === selected) {
        ctx.strokeStyle = "#16242A";
        ctx.lineWidth = 2 / k;
        ctx.stroke();
      }
      var showLabel = n === selected || n === state.hovered
        || k >= LABEL_ZOOM_ALL || labelSet.has(n.id);
      if (showLabel && !dim) {
        ctx.font = (11 / k) + "px ui-monospace, Consolas, monospace";
        ctx.fillStyle = "#3A4B4F";
        ctx.globalAlpha = 0.95;
        ctx.fillText(n.id, n.x + r + 3 / k, n.y + 3 / k);
      }
    });

    ctx.restore();
  }

  /* ---- zoom / pan ---- */
  var zoom = d3.zoom()
    .scaleExtent([0.15, 10])
    .on("zoom", function (ev) {
      state.transform = ev.transform;
      canvas.classList.add("dragging");
      draw();
    })
    .on("end", function () { canvas.classList.remove("dragging"); });
  d3.select(canvas).call(zoom);

  function nodeAt(clientX, clientY) {
    var rect = canvas.getBoundingClientRect();
    var w = rect.width;
    var h = rect.height;
    var x = (clientX - rect.left - w / 2 - state.transform.x) / state.transform.k;
    var y = (clientY - rect.top - h / 2 - state.transform.y) / state.transform.k;
    return sim.find(x, y, HIT_RADIUS / state.transform.k);
  }

  /* ---- hover tooltip ---- */
  canvas.addEventListener("pointermove", function (ev) {
    var n = nodeAt(ev.clientX, ev.clientY);
    if (n !== state.hovered) {
      state.hovered = n || null;
      draw();
    }
    if (n) {
      tip.replaceChildren(
        el("strong", null, n.id),
        el("div", null, n.type + (n.domain ? " / " + n.domain : "")),
        el("div", null, (n.text || "").slice(0, 120))
      );
      var rect = wrap.getBoundingClientRect();
      tip.style.left = Math.min(ev.clientX - rect.left + 14, rect.width - 310) + "px";
      tip.style.top = (ev.clientY - rect.top + 14) + "px";
      tip.style.display = "block";
    } else {
      tip.style.display = "none";
    }
  });
  canvas.addEventListener("pointerleave", function () {
    tip.style.display = "none";
    state.hovered = null;
    draw();
  });

  /* ---- click select (ignore pans) ---- */
  var downAt = null;
  canvas.addEventListener("pointerdown", function (ev) { downAt = [ev.clientX, ev.clientY]; });
  canvas.addEventListener("click", function (ev) {
    if (downAt) {
      var moved = Math.hypot(ev.clientX - downAt[0], ev.clientY - downAt[1]);
      if (moved > CLICK_SLOP_PX) return;
    }
    state.selected = nodeAt(ev.clientX, ev.clientY) || null;
    renderAside();
    draw();
  });

  /* ---- details panel ---- */
  function fieldRow(key, value) {
    var f = el("div", "field");
    f.appendChild(el("span", "k", key));
    f.appendChild(document.createTextNode(value));
    return f;
  }

  function renderAside() {
    var n = state.selected;
    if (!n) {
      aside.replaceChildren(
        el("h3", null, "Node details"),
        el("p", "empty", "Click a node to inspect it: properties, incident edges, and neighbors you can walk to.")
      );
      return;
    }
    var frag = [];
    frag.push(el("h3", null, n.id));
    frag.push(el("div", "meta", n.type
      + (n.domain ? " / " + n.domain : "")
      + (n.severity ? " / " + n.severity : "")
      + (n.mandatory ? " / mandatory" : "")
      + " / " + (n.provenance || "hand-authored")));
    if (n.trigger) frag.push(fieldRow("When", n.trigger));
    if (n.text) frag.push(fieldRow("Statement", n.text));
    frag.push(fieldRow("Connections in this view", String(state.degree.get(n.id) || 0)));

    var groups = new Map();
    state.links.forEach(function (l) {
      var out = l.source.id === n.id;
      var into = l.target.id === n.id;
      if (!out && !into) return;
      var key = l.type + (out ? " (out)" : " (in)");
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(out ? l.target : l.source);
    });
    Array.from(groups.keys()).sort().forEach(function (key) {
      var g = el("div", "edgegroup");
      g.appendChild(el("span", "k", key));
      groups.get(key).forEach(function (other) {
        var b = el("button", "nb", other.id);
        b.type = "button";
        b.addEventListener("click", function () {
          state.selected = other;
          renderAside();
          centerOn(other);
        });
        g.appendChild(b);
      });
      frag.push(g);
    });
    aside.replaceChildren.apply(aside, frag);
  }

  function centerOn(n) {
    var t = d3.zoomIdentity.translate(-n.x * 1.6, -n.y * 1.6).scale(1.6);
    d3.select(canvas).transition().duration(400).call(zoom.transform, t);
  }

  /* ---- controls ---- */
  document.querySelectorAll("#graph-presets button").forEach(function (b) {
    b.addEventListener("click", function () {
      state.preset = b.getAttribute("data-preset");
      document.querySelectorAll("#graph-presets button").forEach(function (x) {
        x.setAttribute("aria-pressed", x === b ? "true" : "false");
      });
      rebuild();
    });
  });
  document.getElementById("graph-isolated").addEventListener("change", function (ev) {
    state.hideIsolated = ev.target.checked;
    rebuild();
  });
  document.getElementById("graph-reset").addEventListener("click", function () {
    d3.select(canvas).transition().duration(300).call(zoom.transform, d3.zoomIdentity);
  });
  searchBox.addEventListener("keydown", function (ev) {
    if (ev.key !== "Enter") return;
    var q = searchBox.value.trim().toUpperCase();
    if (!q) return;
    var hit = state.nodes.find(function (n) { return n.id.toUpperCase() === q; })
      || state.nodes.find(function (n) { return n.id.toUpperCase().indexOf(q) !== -1; });
    if (hit) {
      state.selected = hit;
      renderAside();
      centerOn(hit);
    }
  });

  /* ---- legend with live counts ---- */
  var legend = document.getElementById("graph-legend");
  var counts = {};
  DATA.nodes.forEach(function (n) { counts[n.type] = (counts[n.type] || 0) + 1; });
  Object.keys(TYPE_COLORS).forEach(function (t) {
    if (!counts[t]) return;
    var chip = el("span", "chip");
    var sw = el("span", "swatch");
    sw.style.background = TYPE_COLORS[t];
    chip.appendChild(sw);
    chip.appendChild(document.createTextNode(t + " (" + counts[t] + ")"));
    legend.appendChild(chip);
  });

  window.addEventListener("resize", resize);
  resize();
  rebuild();
})();
