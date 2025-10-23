// Public API + small wiring. No app specifics here.
(function(){
  const DEBUG = !!window.DEBUG;

  // --- helpers (kept small)
  function has(fn){ return typeof fn === 'function'; }

  function deriveClientName(card){
    let name = (card.getAttribute('data-client') || '').trim();
    if (!name) name = (card.querySelector('[data-client-name]')?.getAttribute('data-client-name') || '').trim();
    if (!name) name = (card.querySelector('.modal-header h2, .chart-title, .modal-title, [data-title], h2, h3')?.textContent || '').trim();
    if (!name) name = (card.querySelector('input[name="client_full_name"], input[name="client_name"]')?.value || '').trim();
    if (name && !card.getAttribute('data-client')) card.setAttribute('data-client', name);
    return name;
  }

  function collectSheets(Core, card){
    const sheets = {};
    if (has(Core.collectProfileFromCard))        sheets.profile       = { data: Core.collectProfileFromCard(card) || [] };
    else if (has(window.collectProfile))         sheets.profile       = { data: window.collectProfile() || [] };
    if (has(Core.collectMeasuresFromCard))       sheets.measures      = { data: Core.collectMeasuresFromCard(card) || [] };
    if (has(Core.collectWorkoutFromCard))        sheets.workout       = { data: Core.collectWorkoutFromCard(card)  || [] };
    if (has(Core.collectWorkoutRev1FromCard))    sheets.workout_rev1  = { data: Core.collectWorkoutRev1FromCard(card) || [] };
    if (has(Core.collectNutritionFromCard))      sheets.nutrition     = { columns:['Date','Type','Notes'], data: Core.collectNutritionFromCard(card) || [] };
    if (has(Core.collectCommunicationFromCard))  sheets.communication = { columns:['Date','Type','Notes'], data: Core.collectCommunicationFromCard(card) || [] };
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

  // --- public surface
  const Autosave = {
    _impl: null,
    useImplementation(obj){ this._impl = obj || null; },
    isEnabled(){ return !!(this._impl && this._impl.enabled === true); },

    attach(card, clientNameArg){
      const Core = window.ChartApp || window.Core || {};
      if (!card || !(card instanceof HTMLElement)) return;
      if (card.__autosaveWired) return;

      let clientName = (clientNameArg || '').trim();
      if (!clientName) clientName = deriveClientName(card);

      const getState = () => {
        if (!clientName) clientName = deriveClientName(card);
        if (!clientName) {
          DEBUG && console.warn('[autosave] No client name; skipping for this card.', card);
          return null;
        }
        const sheets = collectSheets(Core, card);
        return { clientName, sheets };
      };

      const saveCore = () => {
        const state = getState();
        if (!state) return;
        try {
          mirrorFlagsToWrapper(card); // keep wrapper data in sync
          if (Autosave._impl && typeof Autosave._impl.save === 'function') {
            Autosave._impl.save(card, state);
          } else if (DEBUG) {
            console.debug('[autosave] no impl set; skipping', state);
          }
        } catch (err) {
          console.error('[autosave] impl error', err);
        }
      };

      // Debounce (keep your original feel ~700ms)
      const deb = (Core.debounceSmart)
        ? Core.debounceSmart(saveCore, 700)
        : (function(fn, ms){ let t; const f = function(){ clearTimeout(t); t = setTimeout(fn, ms); }; f.flush = fn; return f; })(saveCore, 700);

      card.__saveDebounced = deb;

      function maybeSave(){ if (!window.__rev1SuppressAutosave) deb(); }
      const delegate = (e) => {
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

      // seed flags once
      if (!card.hasAttribute('data-flag-nutrition') ||
          !card.hasAttribute('data-flag-focus') ||
          !card.hasAttribute('data-flag-goal')) {
        mirrorFlagsToWrapper(card);
      }

      if (Autosave._impl && typeof Autosave._impl.afterAttach === 'function') {
        Autosave._impl.afterAttach(card);
      }
    },

    detach(card){
      if (!card || !card.__autosaveWired) return;
      const h = card.__delegatedHandler;
      if (h) {
        card.removeEventListener('input', h, true);
        card.removeEventListener('change', h, true);
        card.removeEventListener('blur', h, true);
      }
      delete card.__delegatedHandler;
      delete card.__autosaveWired;
      delete card.__saveDebounced;
      if (this._impl && typeof this._impl.afterDetach === 'function') {
        this._impl.afterDetach(card);
      }
    },

    // convenience: wire current + future .chart-card nodes
    wireAll(){
      document.querySelectorAll('.chart-card').forEach((el)=> Autosave.attach(el));
      const mo = new MutationObserver((muts)=>{
        muts.forEach(m=>{
          m.addedNodes && m.addedNodes.forEach(node=>{
            if (!(node instanceof HTMLElement)) return;
            if (node.matches && node.matches('.chart-card')) Autosave.attach(node);
            node.querySelectorAll && node.querySelectorAll('.chart-card').forEach(Autosave.attach);
          });
        });
      });
      mo.observe(document.body, { childList:true, subtree:true });
      this._mo = mo;
    }
  };

  window.Autosave = Autosave;

  // auto-wire on DOM ready if desired
  document.addEventListener('DOMContentLoaded', ()=> Autosave.wireAll());
})();
