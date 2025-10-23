// client_modal.positioning.js — sidebar-tethered, right-aligned, animation-safe (revised)
(function () {
  if (!window.ClientModal || !window.ClientModal.utils) {
    window.ClientModal = window.ClientModal || { utils: {} };
    window.ClientModal.utils.setXY = (el,x,y)=>{ el.style.setProperty('--x', x+'px'); el.style.setProperty('--y', y+'px'); };
    window.ClientModal.utils.clampIntoViewport = () => {};
    window.ClientModal.utils.capSizeToViewport = () => {};
  }
  const { setXY, clampIntoViewport, capSizeToViewport } = window.ClientModal.utils;

  const RIGHT_MARGIN = 12;
  const LEFT_GUTTER  = 6;
  const TETHER_MS    = 800;
  const MIN_W        = 560;
  const MAX_W        = 1400;

  const SIDEBAR_SELECTORS = ['#client-sidebar','.sidebar','[data-sidebar]','[aria-label="Clients sidebar"]'];
  const TOGGLE_SELECTORS  = ['#sidebar-toggle','[data-sidebar-toggle]','[aria-controls="client-sidebar"]'];

  function widthFractionFor(iw){
    if (iw >= 1600) return 0.64;
    if (iw >= 1440) return 0.66;
    if (iw >= 1280) return 0.70;
    if (iw >= 1120) return 0.74;
    if (iw >= 1024) return 0.78;
    if (iw >=  900) return 0.82;
    if (iw >=  768) return 0.88;
    return 0.96;
  }
  const isInteracting = (el) => el.classList.contains('dragging') || el.classList.contains('resizing');
  const isFree = (el) => el?.dataset?.free === "1";

  const findFirst = (sels) => sels.map((s)=>document.querySelector(s)).find(Boolean) || null;
  const findSidebar = () => findFirst(SIDEBAR_SELECTORS);
  const findToggle  = () => findFirst(TOGGLE_SELECTORS);

  const readHeaderHeight = () => {
    const root = getComputedStyle(document.documentElement);
    return parseInt(root.getPropertyValue('--header-h')) || 64;
  };

  function sidebarRightPx(){
    const sb = findSidebar();
    if (sb) {
      const r = sb.getBoundingClientRect();
      return Math.max(0, Math.min(window.innerWidth, Math.round(r.right)));
    }
    const root = getComputedStyle(document.documentElement);
    const body = document.body;
    const sbWBody = parseInt(getComputedStyle(body).getPropertyValue('--sb-w')) || 0;
    const sbOpen  = parseInt(root.getPropertyValue('--sb-open')) || 280;
    const sbGap   = parseInt(root.getPropertyValue('--sb-gap'))   || 16;
    return (sbWBody || sbOpen) + sbGap;
  }

  function placeAtLayout(el){
    if (el.classList.contains('size-fullscreen')) {
      el.style.width  = window.innerWidth + 'px';
      el.style.height = window.innerHeight + 'px';
      setXY(el, 0, 0);
      return;
    }
    if (el.classList.contains('size-full-under-header')) {
      const headerH = readHeaderHeight();
      el.style.width  = window.innerWidth + 'px';
      el.style.height = Math.max(180, window.innerHeight - headerH) + 'px';
      setXY(el, 0, headerH);
      return;
    }

    const headerH = readHeaderHeight();
    const leftMin = sidebarRightPx() + LEFT_GUTTER;
    const top     = headerH + 8;

    const iw = window.innerWidth;
    const ih = window.innerHeight;

    const rightEd = iw - RIGHT_MARGIN;
    const availH  = Math.max(180, ih - top - RIGHT_MARGIN);

    let targetW;
    if (el.classList.contains('size-full')) {
      targetW = Math.max(240, rightEd - leftMin);
    } else {
      const frac = widthFractionFor(iw);
      const rawW = Math.floor(iw * frac);
      targetW = Math.min(
        Math.max(rawW, MIN_W),
        Math.min(rightEd - leftMin, MAX_W)
      );
    }

    let left  = Math.max(leftMin, rightEd - targetW);
    let width = rightEd - left;

    if (width < 320) {
      width = Math.max(240, rightEd - leftMin);
      left  = rightEd - width;
    }

    el.style.width  = width + 'px';
    el.style.height = availH + 'px';
    setXY(el, left, top);
  }

  const placeSafely = (el) => {
    if (!el) return;
    if (isInteracting(el)) return;
    if (isFree(el)) {                  // stay wherever user dropped it
      clampIntoViewport(el);
      capSizeToViewport(el);
      return;
    }
    placeAtLayout(el);
    clampIntoViewport(el);
    capSizeToViewport(el);
  };

  function startRafTether(el, ms = TETHER_MS){
    if (!el || isFree(el)) return;     // free mode: no sidebar tethering
    let rafId = 0, until = performance.now() + ms, lastRight = -1;

    const tick = () => {
      const nowRight = sidebarRightPx();
      if (lastRight !== -1 && nowRight !== lastRight) {
        until = performance.now() + 120;
      }
      lastRight = nowRight;

      placeSafely(el);
      if (performance.now() < until) rafId = requestAnimationFrame(tick);
    };

    if (el.__rafTetherId) cancelAnimationFrame(el.__rafTetherId);
    el.__rafTetherId = requestAnimationFrame(tick);
  }

  document.addEventListener('clientmodal:opened', (e)=>{
    const el = e.detail?.el; if (!el) return;

    if (!el.classList.contains('size-fullscreen') &&
        !el.classList.contains('size-full-under-header')) {
      el.classList.add('size-xl');
    }

    requestAnimationFrame(() => {
      placeSafely(el);
      requestAnimationFrame(() => placeSafely(el));
    });

    const onWinResize = () => placeSafely(el);
    window.addEventListener('resize', onWinResize, { passive: true });
    el.__pos_onWinResize = onWinResize;

    const sb = findSidebar();
    let sbResizeObs = null;
    const onTrans = () => startRafTether(el);

    if (!isFree(el)) {
      if (sb && 'ResizeObserver' in window) {
        sbResizeObs = new ResizeObserver(() => startRafTether(el, 900));
        sbResizeObs.observe(sb);
      }
      if (sb) {
        sb.addEventListener('transitionstart', onTrans, { passive:true });
        sb.addEventListener('transitionrun',   onTrans, { passive:true });
        sb.addEventListener('transitionend',   onTrans, { passive:true });
      }
      const tog = findToggle();
      const onToggleClick = () => startRafTether(el);
      if (tog) tog.addEventListener('click', onToggleClick, { passive:true });
      el.__pos_onToggleClick = onToggleClick;
    }

    const mo = new MutationObserver((ml) => {
      if (isFree(el)) return;
      for (const m of ml) {
        if (m.type === 'attributes' && m.attributeName === 'class') {
          startRafTether(el);
          break;
        }
      }
    });
    mo.observe(document.body, { attributes: true });

    const onClosed = (ev) => {
      if (ev.detail?.el !== el) return;
      window.removeEventListener('resize', onWinResize);
      document.removeEventListener('clientmodal:closed', onClosed);
      if (el.__pos_onToggleClick) {
        const tog = findToggle();
        if (tog) tog.removeEventListener('click', el.__pos_onToggleClick);
      }
      if (sb) {
        sb.removeEventListener('transitionstart', onTrans);
        sb.removeEventListener('transitionrun',   onTrans);
        sb.removeEventListener('transitionend',   onTrans);
      }
      if (sbResizeObs) sbResizeObs.disconnect();
      mo.disconnect();
      if (el.__rafTetherId) cancelAnimationFrame(el.__rafTetherId);
    };
    document.addEventListener('clientmodal:closed', onClosed, { passive: true });

    if ('ResizeObserver' in window) {
      let done = false;
      const ro = new ResizeObserver(() => {
        if (done) return; done = true;
        placeSafely(el);
        ro.disconnect();
      });
      ro.observe(el);
    }
  });

  document.addEventListener('clientmodal:recenter', (e)=>{
    const el = e.detail?.el;
    if (!el) return;
    placeSafely(el);
  }, { passive: true });
})();
