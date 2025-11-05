// js/charts/client_modal.js — unified controller (drag/resize removed, default mode = "xl")
(function () {
  let openingNow = false;

  /* ---------- FrameLooper (kept for consistency; not required) ---------- */
  function makeFrameLooper(doWork){
    let raf = 0, hasWork = false, lastArgs = null;
    const tick = () => {
      raf = 0;
      if (!hasWork) return;
      hasWork = false;
      doWork.apply(null, lastArgs);
      if (hasWork && !raf) raf = requestAnimationFrame(tick);
    };
    return (...args) => {
      lastArgs = args;
      hasWork = true;
      if (!raf) raf = requestAnimationFrame(tick);
    };
  }

  /* ===== header height + viewport helpers ===== */
  function setHeaderVar() {
    const header = document.querySelector('#app-header, header, .app-header');
    const h = header ? Math.round(header.getBoundingClientRect().height) : 64;
    document.documentElement.style.setProperty('--header-h', `${h}px`);
  }
  function setVHVar() {
    const vh = window.innerHeight * 0.01;
    document.documentElement.style.setProperty('--vh', `${vh}px`);
  }
  setHeaderVar(); setVHVar();
  window.addEventListener('resize', () => { setHeaderVar(); setVHVar(); }, { passive:true });
  window.addEventListener('orientationchange', () => { setHeaderVar(); setVHVar(); }, { passive:true });

  /* ================== Public API ================== */
  window.enableSingleChart  = () => { window.CHARTS_SINGLETON = true;  };
  window.enableMultiCharts  = () => { window.CHARTS_SINGLETON = false; };
  if (typeof window.CHARTS_SINGLETON === "undefined") window.CHARTS_SINGLETON = true;

  // Default to "xl" unless caller overrides
  window.openClientChartByName = function(name, opts = {}) {
    ensureShell();
    if (window.CHARTS_SINGLETON !== false) closeAllModals();
    openClientModal({ name, mode: opts.mode || "xl" });
  };

  window.openClientChart = function (tr) {
    if (!tr || tr.style.display === 'none') return;
    if (openingNow) return;
    openingNow = true; setTimeout(() => (openingNow = false), 150);

    ensureShell();

    const name =
      tr.dataset.name ||
      (tr.querySelector('.client-name-text')?.textContent || '').trim() ||
      (tr.querySelector('td')?.textContent || '').trim();

    // If a row provides data-mode, honor it; otherwise use "xl"
    const mode = tr.dataset.mode || "xl";
    const same = getModalByClient(name);

    if (same) {
      setClientModalMode(same, mode);
      bringToFront(same);
      same.focus?.();
      document.dispatchEvent(new CustomEvent('clientmodal:recenter', { detail: { el: same } }));
      return;
    }

    if (window.CHARTS_SINGLETON !== false) closeAllModals();
    openClientModal({ name, mode });
  };

  window.closeClientChart = function () { closeAllModals(); };

  window.setClientModalMode = function(mode = "xl") {
    const el = getActiveModal();
    if (!el) return;
    setClientModalMode(el, mode);
    document.dispatchEvent(new CustomEvent('clientmodal:recenter', { detail: { el } }));
  };

  /* ================== Shell / Template ================== */
  function ensureShell() {
    if (!document.getElementById('floating-modals')) {
      const layer = document.createElement('div');
      layer.id = 'floating-modals';
      layer.style.position = 'fixed';
      layer.style.inset = '0';
      layer.style.zIndex = '4000';
      layer.style.pointerEvents = 'none';
      document.body.appendChild(layer);
    }

    if (!document.getElementById('client-modal-template')) {
      const tpl = document.createElement('template');
      tpl.id = 'client-modal-template';
      tpl.innerHTML = `
        <div class="client-modal" role="dialog" aria-modal="true" tabindex="-1" aria-label="Client chart" style="pointer-events:auto">
          <div class="modal-header">
            <div id="client-modal-title" class="modal-title"></div>
            <button class="modal-close" type="button" aria-label="Close">×</button>
          </div>
          <div class="modal-body"><div class="loading">Loading…</div></div>
          <div class="modal-footer">
            <button class="modal-close btn btn-dark" type="button">Close</button>
          </div>
        </div>
      `.trim();
      document.body.appendChild(tpl);
    }
  }

  function layerEl() { return document.getElementById('floating-modals'); }
  function getAllModals() { return Array.from(layerEl()?.querySelectorAll('.client-modal') || []); }
  function getActiveModal() { return layerEl()?.querySelector('.client-modal') || null; }
  function getModalByClient(clientName) {
    if (!clientName) return null;
    return getAllModals().find(m => m.dataset.client === clientName) || null;
  }
  function bringToFront(el) { if (el) layerEl()?.appendChild(el); }

  function closeModal(el) {
    if (!el) return;
    try { window.removeEventListener('resize', el.__onResize); } catch {}
    try { el.__ro?.disconnect(); } catch {}
    try { el.__mo?.disconnect(); } catch {}
    try { window.removeEventListener('keydown', el.__onEsc); } catch {}
    try { window.removeEventListener('blur', el.__onWinBlur); } catch {}
    try { document.removeEventListener('visibilitychange', el.__onVis); } catch {}
    el.remove();
    document.dispatchEvent(new CustomEvent('clientmodal:closed', { detail: { el } }));
    if (getAllModals().length === 0) {
      document.body.classList.remove('noscroll');
      document.documentElement.classList.remove('modal-open');
      document.body.classList.remove('modal-open');
    }
  }
  function closeAllModals() {
    getAllModals().forEach(closeModal);
    document.body.classList.remove('noscroll');
    document.documentElement.classList.remove('modal-open');
    document.body.classList.remove('modal-open');
  }

  /* ================== Mode helper ================== */
  function setClientModalMode(el, mode = "xl") {
    const m = (mode || "xl").toLowerCase();
    el.classList.remove('size-xl', 'size-full', 'size-fullscreen', 'size-full-under-header');

    if (m === 'full' || m === 'fullscreen') {
      el.classList.add('size-fullscreen');
    } else if (m === 'under-header' || m === 'underheader') {
      el.classList.add('size-full-under-header');
    } else if (m === 'near-full' || m === 'nearfull') {
      el.classList.add('size-full');
    } else { // default
      el.classList.add('size-xl');
    }
  }

  /* ================== Open ================== */
  function openClientModal({ name, mode = "xl" }) {
    ensureShell();
    if (window.CHARTS_SINGLETON !== false) closeAllModals();

    const layer = layerEl();
    const tpl = document.getElementById('client-modal-template');
    const el = tpl.content.firstElementChild.cloneNode(true);

    // Ensure viewport vars are fresh
    setHeaderVar(); setVHVar();

    setClientModalMode(el, mode);

    el.dataset.client = name || '';
    el.querySelector('.modal-title').textContent = name || 'Client';

    el.__onResize = () => {
      document.dispatchEvent(new CustomEvent('clientmodal:recenter', { detail: { el } }));
    };
    window.addEventListener('resize', el.__onResize, { passive: true });

    const close = () => closeModal(el);
    el.__onEsc = (ev) => (ev.key === 'Escape') && close();
    window.addEventListener('keydown', el.__onEsc);

    // Fail-safe recentering
    el.__onWinBlur = () => document.dispatchEvent(new CustomEvent('clientmodal:recenter', { detail: { el } }));
    window.addEventListener('blur', el.__onWinBlur, { passive: true });
    el.__onVis = () => {};
    document.addEventListener('visibilitychange', el.__onVis, { passive: true });

    el.querySelectorAll('.modal-close').forEach((btn) => btn.addEventListener('click', close, { passive: true }));

    // Double-click header toggles near-full ↔︎ xl
    const headerEl = el.querySelector('.modal-header');
    headerEl?.addEventListener('dblclick', () => {
      if (!el.classList.contains('size-full')) {
        el.classList.remove('size-fullscreen', 'size-full-under-header');
        el.classList.add('size-full');
      } else {
        el.classList.remove('size-full');
        el.classList.add('size-xl');
      }
      document.dispatchEvent(new CustomEvent('clientmodal:recenter', { detail: { el } }));
    }, { passive: true });

    layer.appendChild(el);

    // Lock background scroll + open
    document.body.classList.add('noscroll');
    document.documentElement.classList.add('modal-open');
    document.body.classList.add('modal-open');

    document.dispatchEvent(new CustomEvent('clientmodal:created', { detail: { el } }));
    requestAnimationFrame(() => {
      el.classList.add('show');
      document.dispatchEvent(new CustomEvent('clientmodal:opened', { detail: { el } }));
    });

    if ('ResizeObserver' in window) {
      let done = false;
      el.__ro = new ResizeObserver(() => {
        if (done) return; done = true;
        document.dispatchEvent(new CustomEvent('clientmodal:recenter', { detail: { el } }));
        el.__ro.disconnect();
      });
      el.__ro.observe(el);
    }

    const bodyEl = el.querySelector('.modal-body');
    if ('MutationObserver' in window && bodyEl) {
      let done = false;
      el.__mo = new MutationObserver(() => {
        if (done) return; done = true;
        document.dispatchEvent(new CustomEvent('clientmodal:recenter', { detail: { el } }));
        el.__mo.disconnect();
      });
      el.__mo.observe(bodyEl, { childList: true, subtree: true });
    }

    // Load content via content loader if present; fallback inline
    if (typeof window.__loadClientCard === 'function') {
      window.__loadClientCard(name, el);
    } else {
      loadClientCard(name, el, () => {
        document.dispatchEvent(new CustomEvent('clientmodal:recenter', { detail: { el } }));
      });
    }
  }

  /* ================== Content loader (fallback) ================== */
  async function loadClientCard(name, modalEl, onDone) {
    const bodyEl = modalEl.querySelector('.modal-body');
    try {
      const res = await fetch('/charts/client/' + encodeURIComponent(name) + '/card', {
        headers: { 'X-Requested-With': 'fetch' },
      });
      const html = res.ok ? (await res.text()) : '<div>Unable to load.</div>';
      bodyEl.innerHTML = html || '<div>No data available.</div>';
      rehydrateScripts(bodyEl);
      bodyEl.scrollTop = 0;
    } catch (err) {
      console.error('[client_modal] load error:', err);
      bodyEl.innerHTML = '<div>Unable to load.</div>';
    } finally {
      onDone?.();
    }
  }

  function rehydrateScripts(container) {
    container.querySelectorAll('script').forEach((oldS) => {
      const s = document.createElement('script');
      if (oldS.type) s.type = oldS.type;
      if (oldS.src) s.src = oldS.src;
      else s.textContent = oldS.textContent;
      oldS.replaceWith(s);
    });
  }
})();
