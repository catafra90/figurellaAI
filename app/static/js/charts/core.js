/* Core namespace */
window.ChartApp = window.ChartApp || {};

(function (Core) {
  /* ----- Config / constants ----- */
  Core.COLLAPSE_THRESHOLD = 60;
  Core.IBF_FIRST_URL = "{{ url_for('ibf_bp.ibf_first_contract') }}";
  Core.IBF_FREQ_URL  = "{{ url_for('ibf_bp.ibf_frequency') }}";

  /* GK defaults exactly as you had */
  window.GK_DEFAULTS = { /* paste your GK defaults object TO*, B* here */ };

  /* Safe text converter, shared helpers */
  Core.toText = function (v) {
    if (v == null) return '';
    if (typeof v === 'string' || typeof v === 'number') return String(v);
    if (Array.isArray(v)) return v.map(Core.toText).join(' ');
    if (typeof v === 'object') {
      return String(v.Workout ?? v.workout ?? v.name ?? v.title ?? v.text ?? '');
    }
    return '';
  };

  /* DOM refs */
  Core.el = {
    chartPanel:  document.getElementById('chart-panel'),
    clientPanel: document.getElementById('client-panel'),
    divider:     document.querySelector('.sidebar-divider'),
    searchInput: document.getElementById('clientSearch'),
    onlyCurrent: document.getElementById('onlyCurrent'),
  };

  /* Sidebar filter (safe if controls are missing) */
  Core.applyFilters = function () {
    var q = ((Core.el.searchInput && Core.el.searchInput.value) || '').toLowerCase();
    var only = !!(Core.el.onlyCurrent && Core.el.onlyCurrent.checked);
    document.querySelectorAll('#client-panel tbody tr').forEach(function (tr) {
      var nameCell = tr.querySelector('td.client-name');
      var nameText = ((nameCell && nameCell.dataset.name) || '').toLowerCase();
      var status   = (tr.dataset.status || '').toLowerCase();
      var show = (!q || nameText.indexOf(q) !== -1) && (!only || status === 'current client');
      tr.style.display = show ? '' : 'none';
    });
  };
  /* Bind filters only if inputs exist */
  if (Core.el.searchInput) Core.el.searchInput.addEventListener('input', Core.applyFilters);
  if (Core.el.onlyCurrent) Core.el.onlyCurrent.addEventListener('change', Core.applyFilters);
  Core.applyFilters();

  /* ================= UNLINK SIDEBAR FROM CHART =================
     - Remove drag/collapse behavior that pushed #chart-panel with left offsets
     - Hide/deactivate the divider grip
     - Let CSS (grid or fixed width) control layout
  ================================================================= */
  (function unlinkSidebarFromChart() {
    var clientPanel = Core.el.clientPanel;
    var divider     = Core.el.divider;
    var chartPanel  = Core.el.chartPanel;

    /* Ensure no inline widths/left offsets keep hanging around */
    if (clientPanel) {
      clientPanel.classList.remove('collapsed');
      clientPanel.style.removeProperty('width');
      clientPanel.style.removeProperty('left');
    }
    if (chartPanel) {
      chartPanel.style.removeProperty('left');
    }

    /* Neutralize and hide the divider/grip */
    if (divider) {
      try {
        var clone = divider.cloneNode(true);
        divider.replaceWith(clone);            // drops any listeners that may have been attached
        clone.style.display = 'none';
        clone.style.pointerEvents = 'none';
      } catch (e) {
        divider.style.display = 'none';
        divider.style.pointerEvents = 'none';
      }
    }

    /* Optional: expose a flag for other modules (if any) */
    Core.sidebarLinked = false;
  })();
  /* ================== /UNLINK SIDEBAR FROM CHART ================== */

  /* Public: simple key normalizer */
  Core.normKey = function (s) { return (s || '').trim().toLowerCase(); };

  /* Public: feature flag helper (respect manual-save mode) */
  Core.saveEnabled = function () { return window.CHARTS_AUTOSAVE !== false; };

  /* Public: consistent client-name resolver for any card */
  Core.getClientName = function (card) {
    if (!card) return '';
    var name = (card.getAttribute('data-client') || '').trim();
    if (!name) name = (card.querySelector('[data-client-name]')?.getAttribute('data-client-name') || '').trim();
    if (!name) name = (card.querySelector('.modal-header h2, .chart-title, .modal-title, [data-title], h2, h3')?.textContent || '').trim();
    if (!name) name = (card.querySelector('input[name="client_full_name"], input[name="client_name"]')?.value || '').trim();
    if (name && !card.getAttribute('data-client')) card.setAttribute('data-client', name);
    return name;
  };

})(window.ChartApp);
