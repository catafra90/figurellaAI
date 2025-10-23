// js/chart/client_modal.js — unified controller (buttery drag/resize, iPad-safe)
(function () {
  let openingNow = false;

  /* ---------- FrameLooper: batch many input events into one rAF update ---------- */
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

  /* ================== Public API ================== */
  window.enableSingleChart  = () => { window.CHARTS_SINGLETON = true;  };
  window.enableMultiCharts  = () => { window.CHARTS_SINGLETON = false; };
  if (typeof window.CHARTS_SINGLETON === "undefined") window.CHARTS_SINGLETON = true;

  window.openClientChartByName = function(name, opts = {}) {
    ensureShell();
    if (window.CHARTS_SINGLETON !== false) closeAllModals();
    openClientModal({ name, mode: opts.mode || "default" });
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

    const mode = tr.dataset.mode || "default";
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

  window.setClientModalMode = function(mode = "default") {
    const el = getActiveModal();
    if (!el) return;
    setClientModalMode(el, mode);
    delete el.dataset.free; // re-tether after explicit mode change
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
          <div class="resize-handle" aria-hidden="true"></div>
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
    if (getAllModals().length === 0) document.body.classList.remove('noscroll');
  }
  function closeAllModals() { getAllModals().forEach(closeModal); document.body.classList.remove('noscroll'); }

  /* ================== Mode helper ================== */
  function setClientModalMode(el, mode = "default") {
    const m = (mode || "default").toLowerCase();
    el.classList.remove('size-xl', 'size-full', 'size-fullscreen', 'size-full-under-header');
    delete el.dataset.free;
    if (m === 'full') {
      el.classList.add('size-fullscreen');           // true fullscreen
    } else if (m === 'under-header' || m === 'underheader') {
      el.classList.add('size-full-under-header');    // fills below header
    } else if (m === 'near-full' || m === 'nearfull') {
      el.classList.add('size-full');                 // near-full preset
    } else {
      el.classList.add('size-xl');                   // larger default
    }
  }

  /* ================== Open ================== */
  function openClientModal({ name, mode = "default" }) {
    ensureShell();
    if (window.CHARTS_SINGLETON !== false) closeAllModals();

    const layer = layerEl();
    const tpl = document.getElementById('client-modal-template');
    const el = tpl.content.firstElementChild.cloneNode(true);

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

    // Fail-safe interaction cleanup (prevents "stuck" on iPad)
    el.__onWinBlur = () => document.dispatchEvent(new CustomEvent('clientmodal:recenter', { detail: { el } }));
    window.addEventListener('blur', el.__onWinBlur, { passive: true });
    el.__onVis = () => {
      if (document.visibilityState !== 'visible') {
        el.classList.remove('dragging','resizing');
        document.body.classList.remove('drag-active');
      }
    };
    document.addEventListener('visibilitychange', el.__onVis, { passive: true });

    el.querySelectorAll('.modal-close').forEach((btn) => btn.addEventListener('click', close, { passive: true }));

    // Toggle near-full on dblclick header
    const headerEl = el.querySelector('.modal-header');
    headerEl?.addEventListener('dblclick', () => {
      delete el.dataset.free;
      if (!el.classList.contains('size-full')) {
        el.classList.remove('size-fullscreen', 'size-full-under-header');
        el.classList.add('size-full');
      } else {
        el.classList.remove('size-full');
        el.classList.add('size-xl');
      }
      document.dispatchEvent(new CustomEvent('clientmodal:recenter', { detail: { el } }));
    }, { passive: true });

    makeDraggable(el, headerEl);
    makeResizable(el, el.querySelector('.resize-handle'));

    layer.appendChild(el);
    document.body.classList.add('noscroll');

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

  /* ================== Content loader (fallback only) ================== */
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

  /* ================== Drag/Resize helpers (transform-only drag) ================== */
  function getVarPx(el, name) {
    const v = getComputedStyle(el).getPropertyValue(name).trim();
    return v.endsWith('px') ? parseFloat(v) : parseFloat(v || '0') || 0;
  }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

  function makeDraggable(box, handle) {
    if (!box || !handle) return;

    // live state
    let dragging = false, sx = 0, sy = 0, baseX = 0, baseY = 0, bw = 0, bh = 0;
    let ghostX = 0, ghostY = 0;
    let syncTimer = 0;
    const SYNC_MS = 120;

    const applyMove = makeFrameLooper((cx, cy) => {
      const m = 8, vw = innerWidth, vh = innerHeight;
      let nx = baseX + (cx - sx);
      let ny = baseY + (cy - sy);
      nx = Math.max(m, Math.min(vw - m - bw, nx));
      ny = Math.max(m, Math.min(vh - m - bh, ny));
      ghostX = nx; ghostY = ny;
      box.style.transform = `translate3d(${nx}px, ${ny}px, 0)`; // composite only
    });

    function startTrailingSync(){
      if (syncTimer) return;
      syncTimer = setInterval(() => {
        if (!dragging) return;
        box.style.setProperty('--x', `${ghostX}px`);
        box.style.setProperty('--y', `${ghostY}px`);
        document.dispatchEvent(new CustomEvent('clientmodal:recenter', { detail: { el: box } }));
      }, SYNC_MS);
    }
    function stopTrailingSync(){
      if (syncTimer) { clearInterval(syncTimer); syncTimer = 0; }
    }

    const begin = (cx, cy) => {
      dragging = true; box.classList.add('dragging');
      document.body.classList.add('drag-active');
      box.dataset.free = "1";

      baseX = getVarPx(box, '--x');
      baseY = getVarPx(box, '--y');
      sx = cx; sy = cy;

      const r = box.getBoundingClientRect();
      bw = r.width; bh = r.height;

      box.style.willChange = 'transform';
      startTrailingSync();
    };

    const move = (cx, cy) => { if (dragging) applyMove(cx, cy); };

    const end = () => {
      if (!dragging) return;
      dragging = false;
      stopTrailingSync();

      // commit final position, clear inline transform (back to CSS var transform)
      box.style.setProperty('--x', `${ghostX}px`);
      box.style.setProperty('--y', `${ghostY}px`);
      box.style.transform = '';
      box.style.willChange = 'auto';

      box.classList.remove('dragging');
      document.body.classList.remove('drag-active');

      // subtle ease-out
      box.classList.add('ease-release');
      setTimeout(() => box.classList.remove('ease-release'), 140);

      document.dispatchEvent(new CustomEvent('clientmodal:recenter', { detail: { el: box } }));
      unbind();
    };

    function unbind() {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      window.removeEventListener('touchmove', onTouchMove);
      window.removeEventListener('touchend', onTouchEnd);
      window.removeEventListener('touchcancel', onTouchEnd);
    }

    const onMouseMove = (e) => { e.preventDefault?.(); move(e.clientX, e.clientY); };
    const onMouseUp   = () => end();
    const onTouchMove = (e) => { const t = e.touches?.[0]; if (!t) return; e.preventDefault?.(); move(t.clientX, t.clientY); };
    const onTouchEnd  = () => end();

    if ('PointerEvent' in window) {
      handle.addEventListener('pointerdown', (ev) => {
        if (ev.button !== undefined && ev.button !== 0) return;
        handle.setPointerCapture?.(ev.pointerId);
        begin(ev.clientX, ev.clientY);

        const onMove = (e) => {
          const list = (typeof e.getCoalescedEvents === 'function') ? e.getCoalescedEvents() : null;
          if (list && list.length) {
            const last = list[list.length - 1];
            move(last.clientX, last.clientY);
          } else {
            move(e.clientX, e.clientY);
          }
          e.preventDefault?.();
        };
        const onUp = () => {
          handle.releasePointerCapture?.(ev.pointerId);
          handle.removeEventListener('pointermove', onMove);
          handle.removeEventListener('pointerup', onUp);
          handle.removeEventListener('pointercancel', onUp);
          end();
        };
        handle.addEventListener('pointermove', onMove, { passive:false });
        handle.addEventListener('pointerup', onUp,   { passive:true });
        handle.addEventListener('pointercancel', onUp, { passive:true });
      }, { passive:false });
    } else {
      handle.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        begin(e.clientX, e.clientY);
        window.addEventListener('mousemove', onMouseMove, { passive:false });
        window.addEventListener('mouseup', onMouseUp, { passive:true });
        e.preventDefault?.();
      }, { passive:false });

      handle.addEventListener('touchstart', (e) => {
        const t = e.touches && e.touches[0]; if (!t) return;
        begin(t.clientX, t.clientY);
        window.addEventListener('touchmove', onTouchMove, { passive:false });
        window.addEventListener('touchend', onTouchEnd, { passive:true });
        window.addEventListener('touchcancel', onTouchEnd, { passive:true });
        e.preventDefault?.();
      }, { passive:false });
    }

    window.addEventListener('resize', () => {
      document.dispatchEvent(new CustomEvent('clientmodal:recenter', { detail: { el: box } }));
    }, { passive: true });
  }

  function makeResizable(box, handle) {
    if (!box || !handle) return;

    let sx = 0, sy = 0, sw = 0, sh = 0, resizing = false;

    const applySize = makeFrameLooper((cx, cy) => {
      const m = 8;
      const x = getVarPx(box, '--x'), y = getVarPx(box, '--y');
      const vw = innerWidth, vh = innerHeight;
      const maxW = Math.max(240, vw - m - x);
      const maxH = Math.max(180, vh - m - y);
      let w = Math.max(420, sw + (cx - sx));
      let h = Math.max(260, sh + (cy - sy));
      w = Math.min(w, maxW);
      h = Math.min(h, maxH);
      box.style.willChange = 'width, height';
      box.style.width  = w + 'px';
      box.style.height = h + 'px';
    });

    const begin = (cx, cy) => {
      const r = box.getBoundingClientRect();
      sw = r.width; sh = r.height;
      sx = cx; sy = cy;
      resizing = true;
      box.classList.add('resizing');
      document.body.classList.add('drag-active');
    };
    const move = (cx, cy) => { if (resizing) applySize(cx, cy); };
    const end = () => {
      if (!resizing) return;
      resizing = false;
      box.style.willChange = 'auto';
      box.classList.remove('resizing');
      document.body.classList.remove('drag-active');
      document.dispatchEvent(new CustomEvent('clientmodal:recenter', { detail: { el: box } }));
      unbind();
    };
    function unbind(){
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      window.removeEventListener('touchmove', onTouchMove);
      window.removeEventListener('touchend', onTouchEnd);
      window.removeEventListener('touchcancel', onTouchEnd);
    }

    const onMouseMove = (e) => { e.preventDefault?.(); move(e.clientX, e.clientY); };
    const onMouseUp   = () => end();
    const onTouchMove = (e) => { const t = e.touches?.[0]; if (!t) return; e.preventDefault?.(); move(t.clientX, t.clientY); };
    const onTouchEnd  = () => end();

    if ('PointerEvent' in window) {
      handle.addEventListener('pointerdown', (ev) => {
        if (ev.button !== undefined && ev.button !== 0) return;
        handle.setPointerCapture?.(ev.pointerId);
        begin(ev.clientX, ev.clientY);

        const onMove = (e) => {
          const list = (typeof e.getCoalescedEvents === 'function') ? e.getCoalescedEvents() : null;
          if (list && list.length) {
            const last = list[list.length - 1];
            move(last.clientX, last.clientY);
          } else {
            move(e.clientX, e.clientY);
          }
          e.preventDefault?.();
        };
        const onUp = () => {
          handle.releasePointerCapture?.(ev.pointerId);
          handle.removeEventListener('pointermove', onMove);
          handle.removeEventListener('pointerup', onUp);
          handle.removeEventListener('pointercancel', onUp);
          end();
        };
        handle.addEventListener('pointermove', onMove, { passive:false });
        handle.addEventListener('pointerup', onUp, { passive:true });
        handle.addEventListener('pointercancel', onUp, { passive:true });
      }, { passive:false });
      return;
    }

    handle.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return;
      begin(e.clientX, e.clientY);
      window.addEventListener('mousemove', onMouseMove, { passive:false });
      window.addEventListener('mouseup', onMouseUp, { passive:true });
      e.preventDefault?.();
    }, { passive:false });

    handle.addEventListener('touchstart', (e) => {
      const t = e.touches?.[0]; if (!t) return;
      begin(t.clientX, t.clientY);
      window.addEventListener('touchmove', onTouchMove, { passive:false });
      window.addEventListener('touchend', onTouchEnd, { passive:true });
      window.addEventListener('touchcancel', onTouchEnd, { passive:true });
      e.preventDefault?.();
    }, { passive:false });
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
