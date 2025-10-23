// js/chart/client_modal.core.js — silky drag/resize + iPad fail-safes
(function () {
  const LAYER_ID = 'floating-modals';
  const TPL_ID   = 'client-modal-template';

  if (typeof window.CHARTS_SINGLETON === 'undefined') window.CHARTS_SINGLETON = true;

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

  const API = {
    ensureShell,
    createModal,
    open({ title }) { return openModal({ title }); },
    closeAll,
    getAll,
    getByTitle,
    bringToFront,
    enableSingle: () => (window.CHARTS_SINGLETON = true),
    enableMulti:  () => (window.CHARTS_SINGLETON = false),
    utils: { setXY, clampIntoViewport, capSizeToViewport, placeWithinViewport },
  };
  window.ClientModal = API;

  function ensureShell() {
    if (!document.getElementById(LAYER_ID)) {
      const layer = document.createElement('div');
      layer.id = LAYER_ID;
      Object.assign(layer.style, {
        position: 'fixed',
        inset: '0',
        zIndex: '4000',
        pointerEvents: 'none'
      });
      document.body.appendChild(layer);
    }
    if (!document.getElementById(TPL_ID)) {
      const tpl = document.createElement('template');
      tpl.id = TPL_ID;
      tpl.innerHTML = `
        <div class="client-modal" role="dialog" aria-modal="true" tabindex="-1" style="pointer-events:auto">
          <div class="modal-header">
            <div class="modal-title"></div>
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
    document.body.classList.remove('noscroll');
  }
  function closeAll() { getAll().forEach(closeModal); document.body.classList.remove('noscroll'); }

  function createModal({ title = 'Client' } = {}) {
    ensureShell();
    if (window.CHARTS_SINGLETON !== false) closeAll();

    const tpl = document.getElementById(TPL_ID);
    const el = tpl.content.firstElementChild.cloneNode(true);
    el.querySelector('.modal-title').textContent = title;

    // Close wiring
    const onEsc = (ev) => (ev.key === 'Escape') && close();
    const close = () => {
      try { window.removeEventListener('keydown', onEsc); } catch {}
      closeModal(el);
      document.dispatchEvent(new CustomEvent('clientmodal:closed', { detail: { el } }));
    };
    el.querySelectorAll('.modal-close').forEach((b) => b.addEventListener('click', close, { passive: true }));
    window.addEventListener('keydown', onEsc);

    // Fail-safe end of interactions (prevents "stuck" on iPad)
    el.__onWinBlur = () => document.dispatchEvent(new CustomEvent('clientmodal:recenter', { detail: { el } }));
    window.addEventListener('blur', el.__onWinBlur, { passive: true });
    el.__onVis = () => {
      if (document.visibilityState !== 'visible') {
        el.classList.remove('dragging','resizing');
        document.body.classList.remove('drag-active');
      }
    };
    document.addEventListener('visibilitychange', el.__onVis, { passive: true });

    // Drag + resize
    makeDraggable(el, el.querySelector('.modal-header'));
    makeResizable(el, el.querySelector('.resize-handle'));

    // Double-click header to toggle near-full & re-tether
    el.querySelector('.modal-header')?.addEventListener('dblclick', () => {
      el.dataset.free && delete el.dataset.free;
      el.classList.toggle('size-full');
      if (!el.classList.contains('size-full')) el.classList.add('size-xl');
      document.dispatchEvent(new CustomEvent('clientmodal:recenter', { detail: { el } }));
    }, { passive: true });

    layer().appendChild(el);
    requestAnimationFrame(() => {
      el.classList.add('show', 'opening');
      setTimeout(() => el.classList.remove('opening'), 260);
    });

    document.dispatchEvent(new CustomEvent('clientmodal:created', { detail: { el } }));
    return el;
  }

  function openModal({ title }) {
    if (window.CHARTS_SINGLETON !== false) {
      const same = getByTitle(title);
      if (same) {
        same.focus?.();
        bringToFront(same);
        document.dispatchEvent(new CustomEvent('clientmodal:opened', { detail: { el: same, reused: true } }));
        return same;
      }
    }
    const el = createModal({ title });
    document.dispatchEvent(new CustomEvent('clientmodal:opened', { detail: { el } }));
    return el;
  }

  // helpers
  function getVarPx(el, name) {
    const v = getComputedStyle(el).getPropertyValue(name).trim();
    return v.endsWith('px') ? parseFloat(v) : parseFloat(v || '0') || 0;
  }
  function setXY(el, x, y) { el.style.setProperty('--x', x + 'px'); el.style.setProperty('--y', y + 'px'); }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

  function clampIntoViewport(el) {
    const r = el.getBoundingClientRect();
    const m = 8, vw = innerWidth, vh = innerHeight;
    const x = clamp(getVarPx(el, '--x'), m, vw - m - r.width);
    const y = clamp(getVarPx(el, '--y'), m, vh - m - r.height);
    setXY(el, x, y);
  }
  function capSizeToViewport(el) {
    const m = 8, x = getVarPx(el, '--x'), y = getVarPx(el, '--y');
    const maxW = Math.max(240, innerWidth - m - x);
    const maxH = Math.max(180, innerHeight - m - y);
    const r = el.getBoundingClientRect();
    if (r.width > maxW)  el.style.width  = Math.floor(maxW) + 'px';
    if (r.height > maxH) el.style.height = Math.floor(maxH) + 'px';
  }
  function placeWithinViewport(el, x, y) {
    const r = el.getBoundingClientRect(), m = 8;
    const clampedX = clamp(x, m, innerWidth - m - r.width);
    const clampedY = clamp(y, m, innerHeight - m - r.height);
    setXY(el, clampedX, clampedY);
  }

  /* ================== Drag / Resize (rAF-smoothed) ================== */
  function makeDraggable(box, handle) {
    if (!box || !handle) return;

    let dragging = false, sx = 0, sy = 0, sl = 0, st = 0, bw = 0, bh = 0;

    const applyMove = makeFrameLooper((cx, cy) => {
      const m = 8, vw = innerWidth, vh = innerHeight;
      let nx = sl + (cx - sx), ny = st + (cy - sy);
      nx = Math.max(m, Math.min(vw - m - bw, nx));
      ny = Math.max(m, Math.min(vh - m - bh, ny));
      box.style.willChange = 'transform';
      box.style.transform = `translate3d(${nx}px, ${ny}px, 0)`; // visual
      setXY(box, nx, ny);                                      // source of truth
    });

    const begin = (cx, cy) => {
      dragging = true;
      box.classList.add('dragging');
      document.body.classList.add('drag-active');
      box.dataset.free = "1";
      sx = cx; sy = cy;
      sl = getVarPx(box, '--x'); st = getVarPx(box, '--y');
      const r = box.getBoundingClientRect(); bw = r.width; bh = r.height; // cache once
    };
    const move = (cx, cy) => { if (dragging) applyMove(cx, cy); };
    const end = () => {
      if (!dragging) return;
      dragging = false;
      box.classList.remove('dragging');
      document.body.classList.remove('drag-active');
      box.style.willChange = 'auto';
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
        const t = e.touches?.[0]; if (!t) return;
        begin(t.clientX, t.clientY);
        window.addEventListener('touchmove', onTouchMove, { passive:false });
        window.addEventListener('touchend', onTouchEnd, { passive:true });
        window.addEventListener('touchcancel', onTouchEnd, { passive:true });
        e.preventDefault?.();
      }, { passive:false });
    }

    window.addEventListener('resize', () => clampIntoViewport(box), { passive: true });
  }

  function makeResizable(box, handle) {
    if (!box || !handle) return;

    let sx = 0, sy = 0, sw = 0, sh = 0, resizing = false;

    const applySize = makeFrameLooper((cx, cy) => {
      const m = 8;
      const x = getVarPx(box, '--x'), y = getVarPx(box, '--y');
      const maxW = Math.max(240, innerWidth  - m - x);
      const maxH = Math.max(180, innerHeight - m - y);
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
      capSizeToViewport(box);
      box.classList.remove('resizing');
      document.body.classList.remove('drag-active');
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
})();
