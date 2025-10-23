/* static/js/charts/loader.js (revised: edit removed + autosave hard-off by default) */
(function(Core){
  Core = window.ChartApp = window.ChartApp || Core || {};
  var chartPanel = Core.el && Core.el.chartPanel ? Core.el.chartPanel : document.getElementById('chart-panel');

  // feature flag helpers (fallbacks if Core helpers weren't added)
  // ⛔️ IMPORTANT: default is OFF while refactoring; must be explicitly turned on.
  function saveEnabled(){
    // Global kill switch from templates/base.html
    if (window.SAVES_ENABLED === false) return false;
    // Legacy flag used by older codepaths
    if (window.CHARTS_AUTOSAVE === false) return false;

    // If modular Autosave exists, defer to it
    if (window.Autosave && typeof window.Autosave.isEnabled === 'function') {
      try { return !!window.Autosave.isEnabled(); } catch(_) {}
    }

    // Nothing explicitly enabled → stay OFF by default during refactor
    return false;
  }

  // --- safeEscape for attribute selectors (older browsers may lack CSS.escape) ---
  var safeEscape = (window.CSS && CSS.escape) ? CSS.escape : function (s) {
    return String(s).replace(/["\\]/g, '\\$&');
  };

  // Track in-flight loads per client (avoid double cards on fast double-click / restore)
  var inflight = new Map(); // key -> Promise

  /* Public API: addCard */
  Core.addCard = function(name, opts){
    opts = opts || {};
    var key = Core.normKey ? Core.normKey(name) : (name || '').trim().toLowerCase();
    if (!key) return Promise.resolve();

    // If a load is already in progress for this client, return that promise
    if (inflight.has(key)) return inflight.get(key);

    // If a card already exists, focus it and exit
    var existing = chartPanel && chartPanel.querySelector('.chart-card[data-client="'+ safeEscape(name) +'"]');
    if (existing) {
      existing.scrollIntoView({behavior:'smooth', block:'nearest', inline:'nearest'});
      var hdr = existing.querySelector('.chart-header');
      if (hdr){ hdr.classList.add('flash'); setTimeout(function(){ hdr.classList.remove('flash'); }, 800); }
      return Promise.resolve();
    }

    // Limit the number of open cards
    if (chartPanel && chartPanel.querySelectorAll('.chart-card').length >= 4) return Promise.resolve();

    // Create the card shell (✎ removed)
    var card = document.createElement('div');
    card.className = 'chart-card panel';
    card.dataset.client = name;
    card.innerHTML = ''
      + '<div class="scale-target">'
      + '  <div class="scale-content">'
      + '    <div class="chart-header">'
      + '      <span class="truncate">'+ name +'</span>'
      + '      <span>'
      + '        <button class="chart-close" title="Close">×</button>'
      + '      </span>'
      + '    </div>'
      + '    <div class="chart-body">Loading...</div>'
      + '  </div>'
      + '</div>';
    chartPanel.appendChild(card);

    // Local UI handlers (✎ handler removed)
    card.querySelector('.chart-close').addEventListener('click', function(){ Core.closeCard(card); });

    // Load content
    var p = Core.loadCardContent(card, name, Number.isInteger(opts.initialTab) ? opts.initialTab : 0)
      .finally(function(){ inflight.delete(key); });
    inflight.set(key, p);
    return p;
  };

  Core.closeCard = function(card){
    // Respect autosave flag: DO NOT flush on close when disabled
    var shouldAutosave = saveEnabled();

    var flushP = (shouldAutosave && card.__saveDebounced && card.__saveDebounced.flush)
      ? card.__saveDebounced.flush()
      : Promise.resolve();

    return flushP.finally(function(){
      card.dispatchEvent(new CustomEvent('card:close'));
      if (card.__delegatedHandler){
        card.removeEventListener('input',  card.__delegatedHandler, true);
        card.removeEventListener('change', card.__delegatedHandler, true);
        card.removeEventListener('blur',   card.__delegatedHandler, true);
      }
      if (card.__ro) { try{ card.__ro.disconnect(); }catch(_){} }
      if (card.__abortController) { try{ card.__abortController.abort(); }catch(_){} }
      card.remove();
    });
  };

  Core.loadCardContent = function(card, name, initialTab){
    var controller = new AbortController();
    card.__abortController = controller;

    return fetch('/charts/client/'+ encodeURIComponent(name), { signal: controller.signal, cache:'no-store' })
      .then(function(res){
        if (!res.ok) throw new Error('HTTP '+res.status);
        return res.text();
      })
      .then(function(html){
        if (!chartPanel || !chartPanel.contains(card)) return;
        var body = card.querySelector('.chart-body');

        // Inject HTML
        var wrapper = document.createElement('div');
        wrapper.innerHTML = html;
        body.innerHTML = '';
        Array.prototype.slice.call(wrapper.childNodes).forEach(function(n){ body.appendChild(n); });

        // Re-exec embedded scripts from partials (frequency/profile helpers)
        (function reexecScripts(root){
          var scripts = Array.prototype.slice.call(root.querySelectorAll('script'));
          scripts.forEach(function(old){
            // avoid re-running marked scripts; skip ES modules here
            if (old.dataset.executed === '1') return;
            if ((old.type || '').toLowerCase() === 'module') return;

            var s = document.createElement('script');
            for (var i = 0; i < old.attributes.length; i++) {
              var a = old.attributes[i];
              if (a.name !== 'data-executed') s.setAttribute(a.name, a.value);
            }
            if (!old.src) s.text = old.text || old.textContent || '';
            s.dataset.executed = '1';
            old.parentNode && old.parentNode.replaceChild(s, old);
          });
        })(body);

        // Initialize features (provided by other small modules)
        if (typeof Core.initTabs === 'function')       Core.initTabs(card, initialTab);
        if (typeof Core.setupScaling === 'function')   Core.setupScaling(card);

        // 🔕 Respect feature flag for autosave & any init that autosaves
        var shouldAutosave = saveEnabled();
        if (shouldAutosave && typeof Core.wireAutosaveForCard === 'function') {
          Core.wireAutosaveForCard(card, name);
        }

        // FIRST SESSION seeding:
        if (typeof Core.initFirstSessionFromIBF === 'function') {
          if (shouldAutosave) {
            Core.initFirstSessionFromIBF(card);
          } else {
            try { Core.initFirstSessionFromIBF(card, { onlyIfEmpty:true, neverSave:true }); } catch(_){}
          }
        }

        // FREQUENCY seeding (safe local-only; never overwrites user text)
        if (typeof Core.initFrequencyForCard === 'function') {
          try { Core.initFrequencyForCard(card, { onlyIfEmpty:true }); } catch(_){}
        }

        if (typeof Core.enableRowReorder === 'function')     Core.enableRowReorder(card);

        // Keep existing behavior: returns Promise from Rev1 init
        return (typeof Core.initWorkoutRev1 === 'function') ? Core.initWorkoutRev1(card) : Promise.resolve();
      })
      .catch(function(err){
        if (!controller.signal.aborted){
          var body2 = card.querySelector('.chart-body');
          body2.innerHTML = '<div style="padding:1rem;color:#b91c1c">Failed to load. Click to retry.</div>';
          body2.addEventListener('click', function(){ Core.loadCardContent(card, name, initialTab); }, { once:true });
          console.error('Load error:', err);
        }
      })
      .finally(function(){
        delete card.__abortController;
      });
  };

  /* Sidebar click → open card (defensive) */
  var clientPanelEl = Core.el && Core.el.clientPanel ? Core.el.clientPanel : document.getElementById('client-panel');
  if (clientPanelEl) {
    clientPanelEl.addEventListener('click', function(e){
      var td = e.target.closest('td.client-name'); if (!td) return;
      Core.addCard(td.dataset.name);
    });
  }

  /* Restore previously open cards */
  (function restore(){
    var STORAGE_KEY = 'fig:charts:open-v1';
    try {
      var state = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]') || [];
      state.reduce(function(p, s){
        return p.then(function(){ return Core.addCard(s.name, { initialTab: s.activeTab }); });
      }, Promise.resolve());

      function saveState(){
        var cards = chartPanel.querySelectorAll('.chart-card');
        var out = [];
        cards.forEach(function(card){
          var tabs = card.querySelectorAll('.tab-btn'); var active=0;
          tabs.forEach(function(b,i){ if (b.classList.contains('active')) active=i; });
          out.push({ name: card.dataset.client || '', activeTab: active });
        });
        localStorage.setItem(STORAGE_KEY, JSON.stringify(out));
      }
      window.addEventListener('pagehide', saveState);
      window.addEventListener('beforeunload', saveState);
    } catch(_) {}
  })();

})(window.ChartApp);
