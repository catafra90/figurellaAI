// static/js/charts/client_modal.content.js (revised)
(function () {
  // Public entrypoint (reuse the unified opener)
  window.openClientChart = function(tr){
    if (!tr || tr.style.display === 'none') return;
    const name =
      tr.dataset.name ||
      (tr.querySelector('.client-name-text')?.textContent || '').trim() ||
      (tr.querySelector('td')?.textContent || '').trim();

    const mode = (tr.dataset.mode || "default");
    if (typeof window.openClientChartByName === 'function') {
      window.openClientChartByName(name, { mode });
    } else {
      console.warn('[openClientChart] unified opener missing.');
    }
  };

  // ---------- Load client card ----------
  async function loadClientCard(name, modalEl){
    const bodyEl = modalEl.querySelector('.modal-body');
    try {
      const res = await fetch('/charts/client/' + encodeURIComponent(name) + '/card', {
        headers: { 'X-Requested-With': 'fetch' }
      });
      const html = res.ok ? (await res.text()) : '<div>Unable to load.</div>';
      bodyEl.innerHTML = html || '<div>No data available.</div>';
      rehydrateScripts(bodyEl);

      if (typeof window.initMeasuresAsOf === 'function') {
        window.initMeasuresAsOf(modalEl);
      }

      setScrollMode(modalEl);
      bodyEl.scrollTop = 0;

      // Re-place post-inject
      document.dispatchEvent(new CustomEvent('clientmodal:recenter', { detail:{ el: modalEl } }));
    } catch (err) {
      console.error('[client_modal] load error:', err);
      bodyEl.innerHTML = '<div>Unable to load.</div>';
      setScrollMode(modalEl);
    }
  }

  // expose loader for unified opener to call
  window.__loadClientCard = loadClientCard;

  function setScrollMode(modalEl){
    const body = modalEl.querySelector('.modal-body');
    const hasInner =
      !!modalEl.querySelector('.chart-table-scroll') ||
      !!modalEl.querySelector('.chart-card .chart-body') ||
      !!modalEl.querySelector('.tab-panel .tab-scroll');
    body.classList.toggle('no-outer-scroll', !!hasInner);
  }

  function rehydrateScripts(container){
    container.querySelectorAll('script').forEach((oldS)=>{
      const s = document.createElement('script');
      if (oldS.type) s.type = oldS.type;
      if (oldS.src) s.src = oldS.src;
      else s.textContent = oldS.textContent;
      oldS.replaceWith(s);
    });
  }
})();
