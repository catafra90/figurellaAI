/* /static/js/charts/measures_dropdowns.js
   Enhances FA / STEP rows with <select>, NC with a checkbox.
   Works on initial load AND on dynamically-added chart pages.
   Accepts either a .measures-chart element OR any descendant container.
*/
(function () {
  const DROPDOWN_MAP = {
    "STEP": ["", "1","2","3","4","5","MED","DTX","2DV","2DF"],
    "FA":   ["", "Kim","Aleeza","Julie","Chiara"],
  };
  const FLAG_ROWS = ["NC"];

  const isEl = (n) => n && n.nodeType === 1;

  function createSelect(options, currentValue) {
    const sel = document.createElement("select");
    sel.className = "meas-select";
    for (const opt of options) {
      const o = document.createElement("option");
      o.value = String(opt);
      o.textContent = String(opt);
      if (String(opt) === String(currentValue || "")) o.selected = true;
      sel.appendChild(o);
    }
    return sel;
  }
  function createFlag(currentValue) {
    const box = document.createElement("input");
    box.type = "checkbox";
    box.className = "meas-flag";
    const v = String(currentValue || "").toLowerCase();
    if (v === "true" || v === "1" || v === "x" || v === "yes") box.checked = true;
    return box;
  }

  function enhanceOneChart(chartEl) {
    if (!isEl(chartEl)) return;

    // Idempotency: mark the specific table cells we transform, NOT the whole chart
    chartEl.querySelectorAll("tbody tr[data-row-label]").forEach((row) => {
      const label = (row.getAttribute("data-row-label") || "").trim();
      if (DROPDOWN_MAP[label]) {
        const opts = DROPDOWN_MAP[label];
        row.querySelectorAll("td").forEach((td) => {
          if (td.hasAttribute("data-date-cell")) return;
          if (td.__measEnhanced) return; // already converted
          const initial = td.textContent.trim();
          td.textContent = "";
          td.removeAttribute("contenteditable");
          td.appendChild(createSelect(opts, initial));
          td.__measEnhanced = true;
        });
      } else if (FLAG_ROWS.includes(label)) {
        row.querySelectorAll("td").forEach((td) => {
          if (td.hasAttribute("data-date-cell")) return;
          if (td.__measEnhanced) return; // already converted
          const initial = td.textContent.trim();
          td.textContent = "";
          td.removeAttribute("contenteditable");
          td.appendChild(createFlag(initial));
          td.__measEnhanced = true;
        });
      }
    });

    // date click helper (scoped)
    chartEl.addEventListener(
      "click",
      (e) => {
        const td = e.target.closest("td[data-date-cell]");
        if (!td) return;
        const input = td.querySelector('input[type="date"]');
        if (!input) return;
        if (e.target !== input) {
          input.focus({ preventScroll: true });
          if (typeof input.showPicker === "function") {
            try { input.showPicker(); } catch {}
          }
        }
      },
      true
    );
  }

  function findChartRoots(root) {
    const out = new Set();
    // If root IS a .measures-chart, include it
    if (root && root.matches?.(".measures-chart")) out.add(root);
    // Include any descendants that are charts
    root.querySelectorAll?.(".measures-chart").forEach((el) => out.add(el));
    // If root is a chart page (e.g., .chart-page inside a chart), climb to nearest chart
    if (!out.size && root && root.closest) {
      const nearest = root.closest(".measures-chart");
      if (nearest) out.add(nearest);
    }
    return Array.from(out);
  }

  function enhanceAllWithin(root = document) {
    findChartRoots(root).forEach(enhanceOneChart);
  }

  // Enhance existing on DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => enhanceAllWithin(document));
  } else {
    enhanceAllWithin(document);
  }

  // Enhance any charts/pages added later
  const obs = new MutationObserver((muts) => {
    for (const m of muts) {
      for (const node of m.addedNodes) {
        if (!isEl(node)) continue;
        enhanceAllWithin(node);
      }
    }
  });
  obs.observe(document.documentElement, { childList: true, subtree: true });

  // Expose a manual hook (works with either a chart root OR a page element)
  window.MeasuresDropdowns = {
    refresh(root) {
      enhanceAllWithin(root || document);
    },
  };
})();
