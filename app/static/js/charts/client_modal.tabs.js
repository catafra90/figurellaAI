// static/js/charts/client_modal.tabs.js — robust tabs + layered cache + bottom bar
(function () {
  const qs  = (s, r=document)=>r.querySelector(s);
  const qsa = (s, r=document)=>Array.from(r.querySelectorAll(s));

  // --- helpers ----------------------------------------------------
  function safeRootFrom(node) {
    return node?.closest?.('.client-modal,[data-client-modal],.modal') || document.querySelector('.client-modal,[data-client-modal],.modal');
  }

  function extractHash(el) {
    // Prefer data-tab-target, else pull #id from href (works for full URLs too)
    const explicit = el.getAttribute('data-tab-target');
    if (explicit) return explicit.startsWith('#') ? explicit.slice(1) : explicit;
    const href = el.getAttribute('href') || '';
    if (!href) return '';
    try {
      const u = href.startsWith('#') ? { hash: href } : new URL(href, window.location.href);
      return (u.hash || '').replace(/^#/, '');
    } catch {
      return href.startsWith('#') ? href.slice(1) : '';
    }
  }

  function getPanel(root, id) {
    if (!id) return null;
    const safe = (window.CSS && CSS.escape) ? CSS.escape(id) : id.replace(/[^a-zA-Z0-9_-]/g,'');
    return qs(`.tab-panel[data-tab="${safe}"]`, root) ||
           qs(`#${safe}.tab-panel`, root) ||
           null;
  }

  function setActiveTab(root, tabId) {
    if (!root) return;
    const wrap   = qs('.tab-panels', root) || root;
    const panels = qsa('.tab-panel', wrap);
    const next   = getPanel(root, tabId) || panels[0];
    if (!next) return;

    requestAnimationFrame(() => {
      panels.forEach(p => p.classList.remove('is-active'));
      next.classList.add('is-active');
    });

    // One-time heavy init hook
    if (!next.__inited) {
      next.__inited = true;
      try { root.dispatchEvent(new CustomEvent('clienttabs:init', { detail:{ panel: next }})); } catch {}
    }
    // Light resume (e.g., charts resize) after paint
    (window.requestIdleCallback || setTimeout)(() => {
      try { root.dispatchEvent(new CustomEvent('clienttabs:resume', { detail:{ panel: next }})); } catch {}
    }, 35);

    upgradeToLayeredIfSafe(wrap, next);
  }

  function upgradeToLayeredIfSafe(wrap, activePanel) {
    if (!wrap || !wrap.classList || wrap.classList.contains('layered')) return;
    const had = activePanel?.classList.contains('is-active');
    if (activePanel && !had) activePanel.classList.add('is-active');
    requestAnimationFrame(() => {
      const h = wrap.getBoundingClientRect().height;
      if (h > 120) wrap.classList.add('layered');
    });
  }

  // ============================== Bottom Bar ===============================
  // Re-implement the “open charts” tabs bar here (no new files)
  const bar = document.getElementById('modal-tabs-bar');

  function initials(title) {
    const m = (title || '').trim().match(/\b[A-Za-z]/g) || [];
    return (m[0] || title?.[0] || '?').toUpperCase();
  }

  function ensureBarChrome() {
    if (!bar || bar.__built) return;
    bar.innerHTML = `
      <button class="tabs-chevron" data-dir="left" aria-label="Scroll left">‹</button>
      <div class="tabs-scroller" role="tablist" aria-label="Open charts"></div>
      <button class="tabs-chevron" data-dir="right" aria-label="Scroll right">›</button>
    `;
    bar.__built = true;

    bar.querySelectorAll('.tabs-chevron').forEach(btn => {
      btn.addEventListener('click', () => {
        const sc = bar.querySelector('.tabs-scroller');
        if (!sc) return;
        const dx = sc.clientWidth * 0.8 * (btn.dataset.dir === 'left' ? -1 : 1);
        sc.scrollBy({ left: dx, behavior: 'smooth' });
      }, { passive: true });
    });
  }

  function getOpenModals() {
    const layer = document.getElementById('floating-modals');
    return Array.from(layer?.querySelectorAll?.('.client-modal') || []);
  }

  function bringToFront(el) {
    const layer = document.getElementById('floating-modals');
    if (el && layer) layer.appendChild(el);
  }

  function rebuildBar() {
    if (!bar) return;
    const mods = getOpenModals();
    if (mods.length === 0) {
      bar.hidden = true;
      bar.innerHTML = '';
      bar.__built = false;
      return;
    }
    ensureBarChrome();
    const scroller = bar.querySelector('.tabs-scroller');
    if (!scroller) return;
    scroller.innerHTML = '';
    bar.hidden = false;

    const activeTop = mods[mods.length - 1]; // last appended = front-most
    mods.forEach((el, idx) => {
      const title = el.querySelector('.modal-title')?.textContent?.trim() || `Client ${idx + 1}`;
      const tab = document.createElement('div');
      tab.className = 'modal-tab' + (el === activeTop ? ' active' : '');
      tab.role = 'tab';
      tab.ariaSelected = el === activeTop ? 'true' : 'false';
      tab.innerHTML = `
        <div class="avatar">${initials(title)}</div>
        <div class="tab-title" title="${title}">${title}</div>
        <button class="tab-close" aria-label="Close">×</button>
      `;

      tab.addEventListener('click', (e) => {
        if (e.target.closest('.tab-close')) {
          // simulate clicking the modal close
          el.querySelector('.modal-close')?.click();
          return;
        }
        // bring to front & retrigger opened (so tabs/panels init/resize)
        bringToFront(el);
        el.focus?.();
        document.dispatchEvent(new CustomEvent('clientmodal:opened', { detail: { el, reused: true } }));
        rebuildBar();
      }, { passive: true });

      scroller.appendChild(tab);
    });
  }

  // ============================== Events ===================================
  // 1) Clicks from tabs (buttons or anchors)
  document.addEventListener('click', (e) => {
    const btn = e.target.closest?.('[data-tab-target], a[href*="#"]'); // accept any href with '#'
    if (!btn) return;

    const id = extractHash(btn);
    if (!id) return;

    const root = safeRootFrom(btn);
    if (!root) return;

    if (!getPanel(root, id)) return; // not our panel
    e.preventDefault();
    setActiveTab(root, id);
  }, { capture: true });

  // 2) When the modal opens, ensure a panel is active and try layering
  document.addEventListener('clientmodal:opened', (e) => {
    const el = e.detail?.el; if (!el) return;
    const wrap = qs('.tab-panels', el) || el;
    let active = qs('.tab-panel.is-active', wrap);
    const first = qs('.tab-panel', wrap);
    if (!active && first) {
      first.classList.add('is-active');
      active = first;
    }
    upgradeToLayeredIfSafe(wrap, active || first);
    rebuildBar();
  }, { passive: true });

  // 3) When a modal closes, update the bottom bar
  document.addEventListener('clientmodal:closed', () => {
    rebuildBar();
  }, { passive: true });

  // 4) Fallback on DOM ready (in case modals are pre-rendered)
  document.addEventListener('DOMContentLoaded', () => {
    qsa('.client-modal,[data-client-modal],.modal').forEach(root => {
      const wrap = qs('.tab-panels', root) || root;
      let active = qs('.tab-panel.is-active', wrap);
      const first = qs('.tab-panel', wrap);
      if (!active && first) {
        first.classList.add('is-active');
        active = first;
      }
      upgradeToLayeredIfSafe(wrap, active || first);
    });
    rebuildBar();
  });

  // Optional public API
  window.ClientTabs = {
    activate(elOrRoot, id) {
      const root = elOrRoot?.closest ? elOrRoot : document.querySelector(elOrRoot);
      setActiveTab(root, id);
    }
  };
})();
