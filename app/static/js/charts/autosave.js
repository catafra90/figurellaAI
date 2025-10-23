/* static/js/charts/autosave.js (revised: hard-off by default; no POSTs when disabled) */
(function(Core){
  Core = window.ChartApp = window.ChartApp || Core || {};
  const DEBUG = !!window.DEBUG;

  // ---- master allow/deny gate (OFF by default while refactoring) ----
  function autosaveAllowed(){
    if (window.SAVES_ENABLED === false) return false;       // global kill switch (templates/base.html)
    if (window.CHARTS_AUTOSAVE === false) return false;     // legacy flag (keep honoring)
    if (window.Autosave && typeof window.Autosave.isEnabled === 'function') {
      try { return !!window.Autosave.isEnabled(); } catch(_) {}
    }
    // Default OFF until you intentionally re-enable
    return false;
  }

  function has(fn){ return typeof fn === 'function'; }

  function deriveClientName(card){
    let name = (card.getAttribute('data-client') || '').trim();
    if (!name) name = (card.querySelector('[data-client-name]')?.getAttribute('data-client-name') || '').trim();
    if (!name) name = (card.querySelector('.modal-header h2, .chart-title, .modal-title, [data-title], h2, h3')?.textContent || '').trim();
    if (!name) name = (card.querySelector('input[name="client_full_name"], input[name="client_name"]')?.value || '').trim();
    if (name && !card.getAttribute('data-client')) card.setAttribute('data-client', name);
    return name;
  }

  function collectSheets(card){
    const sheets = {};
    if (has(Core.collectProfileFromCard)) sheets.profile = { data: Core.collectProfileFromCard(card) || [] };
    else if (has(window.collectProfile))  sheets.profile = { data: window.collectProfile() || [] };

    if (has(Core.collectMeasuresFromCard))      sheets.measures      = { data: Core.collectMeasuresFromCard(card) || [] };
    if (has(Core.collectWorkoutFromCard))       sheets.workout       = { data: Core.collectWorkoutFromCard(card)  || [] };
    if (has(Core.collectWorkoutRev1FromCard))   sheets.workout_rev1  = { data: Core.collectWorkoutRev1FromCard(card) || [] };
    if (has(Core.collectNutritionFromCard))     sheets.nutrition     = { columns:['Date','Type','Notes'], data: Core.collectNutritionFromCard(card) || [] };
    if (has(Core.collectCommunicationFromCard)) sheets.communication = { columns:['Date','Type','Notes'], data: Core.collectCommunicationFromCard(card) || [] };
    return sheets;
  }

  function mirrorFlagsToWrapper(card){
    try {
      const n = card.querySelector('input[name="flag_nutrition"]');
      const f = card.querySelector('input[name="flag_focus_case"]');
      const g = card.querySelector('input[name="flag_goal"]');
      if (n) card.setAttribute('data-flag-nutrition', n.checked ? '1' : '0');
      if (f) card.setAttribute('data-flag-focus',     f.checked ? '1' : '0');
      if (g) card.setAttribute('data-flag-goal',      g.checked ? '1' : '0');
    } catch(_) {}
  }

  Core.wireAutosaveForCard = function(card, clientNameArg){
    // If autosave is not allowed, do NOTHING (no wiring at all)
    if (!autosaveAllowed()) {
      if (DEBUG) console.debug('[autosave] wiring skipped (disabled)');
      return;
    }

    if (!card || !(card instanceof HTMLElement)) return;
    if (card.__autosaveWired) return;

    let clientName = (clientNameArg || '').trim();
    if (!clientName) clientName = deriveClientName(card);

    async function saveCore(){
      if (!clientName) clientName = deriveClientName(card);
      if (!clientName) {
        DEBUG && console.warn('[autosave] No client name; aborting save for this card.', card);
        return;
      }
      const sheets = collectSheets(card);
      DEBUG && console.debug('[save ▶]', clientName, sheets);

      try {
        const res = await fetch('/charts/client/' + encodeURIComponent(clientName) + '/save', {
          method:'POST',
          headers:{ 'Content-Type':'application/json' },
          body: JSON.stringify({ sheets })
        });
        const j = await res.json().catch(()=>({}));
        if (!res.ok || j.status !== 'success') throw new Error(j.message || ('HTTP '+res.status));
        DEBUG && console.debug('[save ✓]', clientName);
        mirrorFlagsToWrapper(card);
      } catch (err) {
        console.error('[autosave] failed', err);
      }
    }

    const deb = Core.debounceSmart
      ? Core.debounceSmart(saveCore, 700)
      : (function(fn, ms){ let t; const f = function(){ clearTimeout(t); t = setTimeout(fn, ms); }; f.flush = fn; return f; })(saveCore, 700);

    card.__saveDebounced = deb;

    function maybeSave(){
      // respect both the global suppress flag and the master allow/deny
      if (!autosaveAllowed()) return;
      if (!window.__rev1SuppressAutosave) deb();
    }

    const delegate = function(e){
      const el = e.target;
      if (!(el instanceof HTMLElement)) return;
      if (el.matches('input, textarea, [contenteditable="true"], select')) maybeSave();
    };
    card.addEventListener('input',  delegate, true);
    card.addEventListener('change', delegate, true);
    card.addEventListener('blur',   delegate, true);
    card.addEventListener('card:close', function(){ deb.flush && deb.flush(); });

    card.__delegatedHandler = delegate;
    card.__autosaveWired = true;

    if (!card.hasAttribute('data-flag-nutrition') ||
        !card.hasAttribute('data-flag-focus') ||
        !card.hasAttribute('data-flag-goal')) {
      mirrorFlagsToWrapper(card);
    }
  };

  // ---- Wire cards only when autosave is allowed ----
  if (autosaveAllowed()) {
    document.querySelectorAll('.chart-card').forEach(Core.wireAutosaveForCard);

    const mo = new MutationObserver(muts=>{
      muts.forEach(m=>{
        m.addedNodes && m.addedNodes.forEach(node=>{
          if (!(node instanceof HTMLElement)) return;
          if (node.matches && node.matches('.chart-card')) Core.wireAutosaveForCard(node);
          node.querySelectorAll && node.querySelectorAll('.chart-card').forEach(Core.wireAutosaveForCard);
        });
      });
    });
    mo.observe(document.body, { childList:true, subtree:true });
  } else {
    if (DEBUG) console.debug('[autosave] global wiring disabled');
  }

})(window.ChartApp);
