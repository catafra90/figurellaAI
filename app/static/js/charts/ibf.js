/* static/js/charts/ibf.js */
window.ChartApp = window.ChartApp || {};

(function (Core) {
  function qs(el, sel)  { return el ? el.querySelector(sel) : null; }
  function qsa(el, sel) { return el ? Array.from(el.querySelectorAll(sel)) : []; }

  function setStatus(card, msg) {
    const s = qs(card, '#freq-status');
    if (s) s.textContent = msg || '';
  }

  function sumMap(keys, map) {
    if (!map) return 0;
    return keys.reduce((acc, k) => {
      const n = parseInt(map[k] ?? map[k + '.'] ?? 0, 10);
      return acc + (isNaN(n) ? 0 : n);
    }, 0);
  }

  function revName(name) {
    const parts = (name || '').split(/\s+/).filter(Boolean);
    return (parts.length >= 2) ? `${parts.at(-1)} ${parts[0]}` : '';
  }

  Core.initFrequencyForCard = function (card) {
    try {
      if (!card || card.__ibfFreqInit) return;
      card.__ibfFreqInit = true;

      const tbl = qs(card, '#frequency-table');
      const cfg = qs(card, '#freq-filters');
      if (!tbl || !cfg) return;

      const base = (cfg.getAttribute('data-fetch-url') || '').trim();

      // Find *this modal's* client name only (NO globals!)
      const modal = card.closest('.client-modal');
      let client =
        (cfg.getAttribute('data-client') || '').trim() ||
        (card.getAttribute('data-client') || '').trim() ||
        (modal?.getAttribute('data-client') || '').trim() ||
        (qs(card, '[data-client-name]')?.getAttribute('data-client-name') || '').trim() ||
        (modal?.querySelector('.modal-title')?.textContent || '').trim();

      if (!base || !client) {
        setStatus(card, 'missing client/base');
        console.debug('[IBF] missing base or client', { base, client, modal });
        return;
      }

      const badge = qs(card, '#current-client');
      if (badge) badge.textContent = client;

      const MONTH_KEYS = qsa(tbl, 'tbody td[data-month]').map(td => td.dataset.month);

      // Make blanks visibly 0 so we know the script ran
      MONTH_KEYS.forEach((m) => {
        const td = qs(tbl, `td[data-month="${m}"]`);
        if (td && !td.textContent.trim()) td.textContent = '0';
      });

      function render(monthMap) {
        MONTH_KEYS.forEach((m) => {
          const td = qs(tbl, `td[data-month="${m}"]`);
          if (!td) return;
          const v = monthMap?.[m] ?? monthMap?.[m + '.'] ?? 0;
          td.textContent = String(v);
        });
      }

      function urlFor(name, y) {
        const u = new URL(base, window.location.origin);
        u.searchParams.set('client', name);
        if (y != null) {
          u.searchParams.set('start', `${y}-01-01`);
          u.searchParams.set('end',   `${y}-12-31`);
        }
        return u.toString();
      }
      function bestUrlFor(name) {
        const bestBase = base.replace(/\/frequency(?:\/)?$/, '/frequency/best');
        const u = new URL(bestBase, window.location.origin);
        u.searchParams.set('client', name);
        return u.toString();
      }
      function fetchMonths(url) {
        setStatus(card, 'loading…');
        console.debug('[IBF] GET', url);
        return fetch(url, {
          headers: { 'Accept': 'application/json' },
          credentials: 'same-origin',
          cache: 'no-store'
        })
          .then(r => r.ok ? r.json() : null)
          .then(j => (j && j.months) ? j.months : null)
          .catch(err => { console.warn('[IBF] fetch error', err); setStatus(card, 'error'); return null; });
      }

      const year = new Date().getFullYear();
      const rev  = revName(client);

      // this year → reversed this year → last year → reversed last year → best-year
      fetchMonths(urlFor(client, year)).then(m1 => {
        if (m1 && sumMap(MONTH_KEYS, m1) > 0) { render(m1); setStatus(card, ''); return; }

        if (rev) {
          return fetchMonths(urlFor(rev, year)).then(m2 => {
            if (m2 && sumMap(MONTH_KEYS, m2) > 0) { render(m2); setStatus(card, ''); return; }

            return fetchMonths(urlFor(client, year - 1)).then(m3 => {
              if (m3 && sumMap(MONTH_KEYS, m3) > 0) { render(m3); setStatus(card, ''); return; }

              if (rev) {
                return fetchMonths(urlFor(rev, year - 1)).then(m4 => {
                  if (m4 && sumMap(MONTH_KEYS, m4) > 0) { render(m4); setStatus(card, ''); return; }
                  return fetchMonths(bestUrlFor(client)).then(mb => { render(mb || {}); setStatus(card, mb ? '' : 'No IBF data'); });
                });
              } else {
                return fetchMonths(bestUrlFor(client)).then(mb => { render(mb || {}); setStatus(card, mb ? '' : 'No IBF data'); });
              }
            });
          });
        }

        return fetchMonths(urlFor(client, year - 1)).then(m3 => {
          if (m3 && sumMap(MONTH_KEYS, m3) > 0) { render(m3); setStatus(card, ''); return; }
          return fetchMonths(bestUrlFor(client)).then(mb => { render(mb || {}); setStatus(card, mb ? '' : 'No IBF data'); });
        });
      });

    } catch (e) {
      console.error('[IBF] initFrequencyForCard failed:', e);
      setStatus(card, 'error');
    }
  };
})(window.ChartApp);
