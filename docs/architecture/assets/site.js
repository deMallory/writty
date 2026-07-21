/* Mermaid rendering + fullscreen pan/zoom viewer for the architecture site. */

var MIN_SCALE = 0.3;
var MAX_SCALE = 8;
var WHEEL_STEP = 1.15;
var BUTTON_STEP = 1.3;

mermaid.initialize({
  startOnLoad: false,
  securityLevel: "loose", /* required for click-to-page links on the index map */
  theme: "base",
  fontFamily: 'system-ui, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  themeVariables: {
    fontSize: "15.5px",
    primaryColor: "#E7F0ED",
    primaryTextColor: "#16242A",
    primaryBorderColor: "#8FAAA2",
    lineColor: "#54706B",
    secondaryColor: "#F6EEDF",
    tertiaryColor: "#EEF2F5",
    clusterBkg: "#F5F8F6",
    clusterBorder: "#C6D3CC",
    edgeLabelBackground: "#FFFFFF",
    nodeTextColor: "#16242A",
  },
  flowchart: {
    useMaxWidth: false,
    curve: "basis",
    padding: 14,
    nodeSpacing: 45,
    rankSpacing: 55,
    /* keeps cluster titles clear of the first node row (the overlap bug) */
    subGraphTitleMargin: { top: 6, bottom: 14 },
  },
  state: { useMaxWidth: false },
});

mermaid.run({ querySelector: "pre.mermaid" }).then(setupLightbox);

/* ---------- fullscreen viewer ---------- */

function el(tag, className, text) {
  var node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function toolButton(action, label, text) {
  var b = el("button", null, text);
  b.type = "button";
  b.setAttribute("data-act", action);
  b.setAttribute("aria-label", label);
  return b;
}

function setupLightbox() {
  var box = el("div", "lightbox");
  var stage = el("div", "stage");
  var canvas = el("div", "canvas");
  var toolbar = el("div", "toolbar");
  var caption = el("div", "caption");
  toolbar.append(
    toolButton("in", "Zoom in", "+"),
    toolButton("out", "Zoom out", "−"),
    toolButton("reset", "Reset view", "Reset"),
    toolButton("close", "Close", "Close ×")
  );
  stage.appendChild(canvas);
  box.append(stage, toolbar, caption);
  document.body.appendChild(box);

  var scale = 1;
  var tx = 0;
  var ty = 0;

  function apply() {
    canvas.style.transform =
      "translate(" + tx + "px," + ty + "px) scale(" + scale + ")";
  }

  function svgSize(svg) {
    var vb = svg.viewBox && svg.viewBox.baseVal;
    if (vb && vb.width && vb.height) return { w: vb.width, h: vb.height };
    var rect = svg.getBoundingClientRect();
    return { w: rect.width || 800, h: rect.height || 500 };
  }

  function fit(svg) {
    var size = svgSize(svg);
    /* open at the largest scale that fits with a margin, but never below 1x */
    scale = Math.max(
      1,
      Math.min((window.innerWidth * 0.9) / size.w, (window.innerHeight * 0.85) / size.h)
    );
    tx = -(size.w * scale) / 2;
    ty = -(size.h * scale) / 2;
    apply();
  }

  function open(figBody, figTitle) {
    var svg = figBody.querySelector("svg");
    if (!svg) return;
    var clone = svg.cloneNode(true);
    clone.removeAttribute("style");
    clone.setAttribute("width", svgSize(clone).w);
    canvas.replaceChildren(clone);
    caption.textContent =
      figTitle + "  (scroll to zoom, drag to pan, Esc to close)";
    box.classList.add("open");
    document.body.style.overflow = "hidden";
    fit(clone);
  }

  function close() {
    box.classList.remove("open");
    canvas.replaceChildren();
    document.body.style.overflow = "";
  }

  function zoomAt(cx, cy, factor) {
    var next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale * factor));
    factor = next / scale;
    /* keep the point under the cursor fixed: canvas origin is viewport center */
    var ox = cx - window.innerWidth / 2;
    var oy = cy - window.innerHeight / 2;
    tx = ox - (ox - tx) * factor;
    ty = oy - (oy - ty) * factor;
    scale = next;
    apply();
  }

  toolbar.addEventListener("click", function (e) {
    var act = e.target.getAttribute("data-act");
    var svg;
    if (act === "close") close();
    if (act === "in") zoomAt(window.innerWidth / 2, window.innerHeight / 2, BUTTON_STEP);
    if (act === "out") zoomAt(window.innerWidth / 2, window.innerHeight / 2, 1 / BUTTON_STEP);
    if (act === "reset") {
      svg = canvas.querySelector("svg");
      if (svg) fit(svg);
    }
  });

  stage.addEventListener("click", function (e) {
    if (e.target === stage) close();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && box.classList.contains("open")) close();
  });

  stage.addEventListener(
    "wheel",
    function (e) {
      e.preventDefault();
      zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? WHEEL_STEP : 1 / WHEEL_STEP);
    },
    { passive: false }
  );

  var dragging = false;
  var lastX = 0;
  var lastY = 0;
  stage.addEventListener("pointerdown", function (e) {
    dragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
    stage.classList.add("dragging");
    stage.setPointerCapture(e.pointerId);
  });
  stage.addEventListener("pointermove", function (e) {
    if (!dragging) return;
    tx += e.clientX - lastX;
    ty += e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    apply();
  });
  stage.addEventListener("pointerup", function (e) {
    dragging = false;
    stage.classList.remove("dragging");
    stage.releasePointerCapture(e.pointerId);
  });

  /* wire every figure */
  document.querySelectorAll("figure.fig").forEach(function (fig) {
    var body = fig.querySelector(".fig-body");
    if (!body) return;
    var num = fig.querySelector(".fig-num");
    var title = fig.querySelector(".fig-title");
    var label =
      (num ? num.textContent + " " : "") + (title ? title.textContent : "");
    body.addEventListener("click", function (e) {
      /* let embedded links inside diagrams (index map) win over the zoom */
      if (e.target.closest("a")) return;
      open(body, label);
    });
  });
}
