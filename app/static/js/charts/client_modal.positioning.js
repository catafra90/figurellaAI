// static/js/charts/client_modal.positioning.js — wide (edge-gutter) placement + iPad/zoom safe
(function () {
  // Ensure utils exist (from core)
  if (!window.ClientModal || !window.ClientModal.utils) {
    window.ClientModal = window.ClientModal || { utils: {} };
    window.ClientModal.utils.setXY = (el,x,y)=>{ el.style.setProperty('--x', x+'px'); el.style.setProperty('--y', y+'px'); };
  }
  const { setXY } = window.ClientModal.utils;

  // ──────────────────────────────────────────────────────────────────────────
  // Layout constants (match CSS gutters)
  // ──────────────────────────────────────────────────────────────────────────
  const EDGE_GUTTER = 16;      // px gutter left/right & bottom
  const TOP_MARGIN  = 12;      // minimal top gap when centering
  const MIN_W       = 560;     // don't shrink below this
  const MAX_W       = 1920;    // hard cap for ultra-wide screens

  // Visual-viewport box (works on zoom & iPad keyboard)
  function vvBox(){
    const vv = window.visualViewport;
    if (vv) {
      return {
        w: Math.round(vv.width),
        h: Math.round(vv.height),
        left: Math.round(vv.pageLeft),
        top:  Math.round(vv.pageTop)
      };
    }
    return {
      w: Math.round(window.innerWidth),
      h: Math.round(window.innerHeight),
      left: Math.round(window.scrollX || 0),
      top:  Math.round(window.scrollY || 0)
    };
  }

  // Throttle placement to once per frame
  let rafId = 0;
  function rafPlace(el){
    if (rafId) return;
    rafId = requestAnimationFrame(() => { rafId = 0; placeSafely(el); });
  }
  function rafPlaceAll(){
    const list = document.querySelectorAll('#floating-modals .client-modal');
    if (!list.length || rafId) return;
    rafId = requestAnimationFrame(() => { rafId = 0; list.forEach(el => placeSafely(el)); });
  }

  function placeAtLayout(el){
    const tabsH   = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--tabs-bar-h')) || 0;
    const headerH = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--header-h')) || 64;
    const { w: iw, h: ih, left: vvx, top: vvy } = vvBox();

    // Fullscreen
    if (el.classList.contains('size-fullscreen')) {
      el.style.width  = iw + 'px';
      el.style.height = ih + 'px';
      setXY(el, vvx, vvy);
      return;
    }

    // Under header (fills width below header)
    if (el.classList.contains('size-full-under-header')) {
      el.style.width  = iw + 'px';
      el.style.height = Math.max(220, ih - headerH) + 'px';
      setXY(el, vvx, vvy + headerH);
      return;
    }

    // Centered preset (size-xl): wide, pinned under header
if (el.classList.contains('size-xl')) {
  const maxWide = Math.min(iw - 2*EDGE_GUTTER, MAX_W);
  const width   = Math.max(MIN_W, maxWide);

  // Respect header at the top and tabs at the bottom
  const topGap   = headerH + 8;                  // ⬅️ sit right below logo/header
  const availH   = Math.max(220, ih - topGap - EDGE_GUTTER - tabsH);
  const targetH  = Math.round(ih * 0.88);
  const height   = Math.min(targetH, availH);

  const left = Math.round(vvx + (iw - width)/2);
  const top  = Math.round(vvy + topGap);         // ⬅️ fixed under header

  el.style.width  = width + 'px';
  el.style.height = height + 'px';
  setXY(el, left, top);
  return;
}


    // Default: near-full, right-aligned below header (legacy behavior but wider)
    const top   = headerH + 8;
    const width = Math.max(MIN_W, Math.min(iw - 2*EDGE_GUTTER, MAX_W));
    const left  = EDGE_GUTTER;
    const availH = Math.max(220, ih - top - EDGE_GUTTER - tabsH);

    el.style.width  = width + 'px';
    el.style.height = availH + 'px';
    setXY(el, vvx + left, vvy + top);
  }

  function placeSafely(el){
    if (!el) return;
    placeAtLayout(el);

    // Final clamp to visual viewport with same gutters
    const r = el.getBoundingClientRect();
    const { w: iw, h: ih, left: vvx, top: vvy } = vvBox();

    let x = parseFloat(getComputedStyle(el).getPropertyValue('--x')) || 0;
    let y = parseFloat(getComputedStyle(el).getPropertyValue('--y')) || 0;

    const minX = vvx + EDGE_GUTTER;
    const maxX = vvx + iw - EDGE_GUTTER - r.width;
    const minY = vvy + EDGE_GUTTER;
    const maxY = vvy + ih - EDGE_GUTTER - r.height;

    x = Math.round(Math.max(minX, Math.min(maxX, x)));
    y = Math.round(Math.max(minY, Math.min(maxY, y)));

    setXY(el, x, y);
  }

  // ── Lifecycle hooks ───────────────────────────────────────────────────────
  document.addEventListener('clientmodal:opened', (e)=>{
    const el = e.detail && e.detail.el; if (!el) return;

    // Normalize to XL (centered wide) unless fullscreen variants are explicit
    if (!el.classList.contains('size-fullscreen') && !el.classList.contains('size-full-under-header')) {
      el.classList.remove('size-full');
      el.classList.add('size-xl');
    }

    // Double-pass for first paint
    requestAnimationFrame(() => { placeSafely(el); requestAnimationFrame(() => placeSafely(el)); });

    const onResize = () => rafPlace(el);
    window.addEventListener('resize', onResize, { passive: true });
    if (window.visualViewport) {
      visualViewport.addEventListener('resize', onResize, { passive: true });
      visualViewport.addEventListener('scroll',  onResize, { passive: true });
    }

    el.__pos_off = () => {
      window.removeEventListener('resize', onResize);
      if (window.visualViewport) {
        visualViewport.removeEventListener('resize', onResize);
        visualViewport.removeEventListener('scroll',  onResize);
      }
    };

    const onClosed = (ev) => {
      if (!ev.detail || ev.detail.el !== el) return;
      el.__pos_off?.();
      document.removeEventListener('clientmodal:closed', onClosed);
    };
    document.addEventListener('clientmodal:closed', onClosed, { passive: true });

    // Extra recenter after keyboard/toolbar/tabs animations
    setTimeout(() => rafPlace(el), 250);
  }, { passive: true });

  document.addEventListener('clientmodal:recenter', (e)=>{
    const el = e.detail && e.detail.el; if (!el) return;
    rafPlace(el);
  }, { passive: true });

  // Recenter ALL open modals when the tabs bar changes
  document.addEventListener('clienttabs:updated', () => {
    rafPlaceAll();
  }, { passive: true });
})();
