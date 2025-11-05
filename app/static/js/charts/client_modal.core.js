// static/js/charts/client_modal.core.js — modal core (no drag/resize, default "xl")
(function () {
  const LAYER_ID = 'floating-modals';
  const TPL_ID   = 'client-modal-template';

  if (typeof window.CHARTS_SINGLETON === 'undefined') window.CHARTS_SINGLETON = true;

  function setHeaderVar() {
    const header = document.querySelector('#app-header, header, .app-header');
    const h = header ? Math.round(header.getBoundingClientRect().height) : 64;
    document.documentElement.style.setProperty('--header-h', `${h}px`);
  }
  function setVHVar() {
    const vv = window.visualViewport;
    const h = Math.round((vv && vv.height) || window.innerHeight);
    document.documentElement.style.setProperty('--vh', (h * 0.01) + 'px');
  }
  setHeaderVar(); setVHVar();
  window.addEventListener('resize', () => { setHeaderVar(); setVHVar(); }, { passive:true });
  window.addEventListener('orientationchange', () => { setHeaderVar(); setVHVar(); }, { passive:true });
  if (window.visualViewport) {
    visualViewport.addEventListener('resize', setVHVar, { passive: true });
    visualViewport.addEventListener('scroll', setVHVar,  { passive: true });
  }

  // expose tiny utils (positioning consumes these)
  function setXY(el, x, y) { el.style.setProperty('--x', x + 'px'); el.style.setProperty('--y', y + 'px'); }
  const API = {
    ensureShell, createModal,
    open({ title, mode = 'xl' }) { return openModal({ title, mode }); },
    closeAll, getAll, getByTitle, bringToFront,
    enableSingle: () => (window.CHARTS_SINGLETON = true),
    enableMulti:  () => (window.CHARTS_SINGLETON = false),
    utils: { setXY },
  };
  window.ClientModal = API;

  function ensureShell() {
    if (!document.getElementById(LAYER_ID)) {
      const layer = document.createElement('div');
      layer.id = LAYER_ID;
      layer.style.position = 'fixed';
      layer.style.inset = '0';
      layer.style.zIndex = '4000';
      layer.style.pointerEvents = 'none';
      document.body.appendChild(layer);
    }
    if (!document.getElementById(TPL_ID)) {
      const tpl = document.createElement('template');
      tpl.id = TPL_ID;
      tpl.innerHTML = `
        <div class="client-modal" role="dialog" aria-modal="true" tabindex="-1" style="pointer-events:auto">
          <div class="modal-header">
            <div class="modal-title"></div>
            <button class="modal-action" type="button" data-open-client-picker
                    title="Open client list" aria-label="Open client list">Clients</button>
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

  function layer() { return document.getElementById(LAYER_ID); }
  function getAll() { return Array.from(layer()?.querySelectorAll('.client-modal') || []); }
  function getByTitle(title) {
    if (!title) return null;
    return getAll().find(m => m.querySelector('.modal-title')?.textContent === title) || null;
  }
  function bringToFront(el) { if (el && layer()) layer().appendChild(el); }

  function closeModal(el) {
    if (!el) return;
    try { window.removeEventListener('resize', el.__onResize); } catch {}
    try { el.__ro?.disconnect(); } catch {}
    try { el.__mo?.disconnect(); } catch {}
    try { window.removeEventListener('keydown', el.__onEsc); } catch {}
    try { window.removeEventListener('blur', el.__onWinBlur); } catch {}
    try { document.removeEventListener('visibilitychange', el.__onVis); } catch {}
    el.remove();
    if (getAll().length === 0) {
      document.body.classList.remove('noscroll');
      document.documentElement.classList.remove('modal-open');
      document.body.classList.remove('modal-open');
    }
  }
  function closeAll() { getAll().forEach(closeModal); }

  function createModal({ title = 'Client', mode = 'xl' } = {}) {
    ensureShell();
    if (window.CHARTS_SINGLETON !== false) closeAll();

    const tpl = document.getElementById(TPL_ID);
    const el = tpl.content.firstElementChild.cloneNode(true);
    el.querySelector('.modal-title').textContent = title;

    // Reset inherited geometry (fixes iPad first-paint offset)
    el.style.removeProperty('width');
    el.style.removeProperty('height');
    el.style.setProperty('--x', '0px');
    el.style.setProperty('--y', '0px');

    // Size preset
    el.classList.remove('size-xl','size-full','size-fullscreen','size-full-under-header');
    if (mode === 'fullscreen' || mode === 'full') {
      el.classList.add('size-fullscreen');
    } else if (mode === 'under-header' || mode === 'underheader') {
      el.classList.add('size-full-under-header');
    } else if (mode === 'near-full' || mode === 'nearfull') {
      el.classList.add('size-full');
    } else {
      el.classList.add('size-xl');
    }

    // Close wiring
    const onEsc = (ev) => (ev.key === 'Escape') && close();
    const close = () => {
      try { window.removeEventListener('keydown', onEsc); } catch {}
      closeModal(el);
      document.dispatchEvent(new CustomEvent('clientmodal:closed', { detail: { el } }));
    };
    el.querySelectorAll('.modal-close').forEach((b) => b.addEventListener('click', close, { passive: true }));
    window.addEventListener('keydown', onEsc);

    // Defensive recenter hooks
    el.__onWinBlur = () => document.dispatchEvent(new CustomEvent('clientmodal:recenter', { detail: { el } }));
    window.addEventListener('blur', el.__onWinBlur, { passive: true });
    el.__onVis = () => {};
    document.addEventListener('visibilitychange', el.__onVis, { passive: true });

    // Header dblclick toggles near-full ↔︎ xl
    el.querySelector('.modal-header')?.addEventListener('dblclick', () => {
      if (!el.classList.contains('size-full')) {
        el.classList.remove('size-fullscreen', 'size-full-under-header');
        el.classList.add('size-full');
      } else {
        el.classList.remove('size-full');
        el.classList.add('size-xl');
      }
      document.dispatchEvent(new CustomEvent('clientmodal:recenter', { detail: { el } }));
    }, { passive: true });

    layer().appendChild(el);

    // Lock background scroll
    document.body.classList.add('noscroll');
    document.documentElement.classList.add('modal-open');
    document.body.classList.add('modal-open');

    requestAnimationFrame(() => {
      el.classList.add('show', 'opening');
      setTimeout(() => el.classList.remove('opening'), 260);
      document.dispatchEvent(new CustomEvent('clientmodal:opened', { detail: { el } }));
    });

    // One-time recenter after first paint & after content hydrate
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

    return el;
  }

  function openModal({ title, mode = 'xl' }) {
    if (window.CHARTS_SINGLETON !== false) {
      const same = getByTitle(title);
      if (same) {
        same.focus?.();
        bringToFront(same);
        document.dispatchEvent(new CustomEvent('clientmodal:opened', { detail: { el: same, reused: true } }));
        return same;
      }
    }
    return createModal({ title, mode });
  }
})();
