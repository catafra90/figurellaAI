// static/js/frequency.js
(function(){
  const BUCKETS = ['freq-0','freq-1-4','freq-5-7','freq-8-11','freq-12p'];
  const inited = new WeakSet();

  function bucketClass(n){
    if (n <= 0 || isNaN(n)) return 'freq-0';
    if (n <= 4)  return 'freq-1-4';
    if (n <= 7)  return 'freq-5-7';
    if (n <= 11) return 'freq-8-11';
    return 'freq-12p';
  }
  function setValAttr(td, n){ td.setAttribute('data-freq-val', String(isNaN(n) ? 0 : n)); }
  function colorize(td, n){
    BUCKETS.forEach(c => td.classList.remove(c));
    td.classList.add(bucketClass(n));
    setValAttr(td, n);
  }
  function colorizeWithPulse(td){
    const raw = (td.textContent || '').trim();
    const n = parseInt(raw, 10);
    const old = parseInt(td.getAttribute('data-freq-val') || 'NaN', 10);
    const changed = (isNaN(old) ? true : (n !== old));

    colorize(td, isNaN(n) ? 0 : n);

    if (changed){
      td.classList.add('freq-just-updated');
      setTimeout(() => td.classList.remove('freq-just-updated'), 950);
    }
  }

  function attachEditingHandlers(table){
    table.addEventListener('input', (e) => {
      const td = e.target.closest('td[data-month]');
      if (td) colorizeWithPulse(td);
    });
    table.addEventListener('blur', (e) => {
      const td = e.target.closest('td[data-month]');
      if (!td) return;
      let s = (td.textContent || '').trim();
      const m = s.match(/-?\d+/);
      const v = m ? parseInt(m[0], 10) : 0;
      td.textContent = String(isNaN(v) ? 0 : v);
      colorizeWithPulse(td);
    }, true);
  }

  function debounce(fn, ms){ let t; return ()=>{ clearTimeout(t); t=setTimeout(fn,ms); }; }

  function observeTable(table){
    const apply = debounce(() => applyFrequencyColors(table), 20);
    new MutationObserver(apply).observe(table.tBodies[0] || table, {
      characterData:true, childList:true, subtree:true
    });
  }

  function applyFrequencyColors(scope){
    (scope || document).querySelectorAll('#frequency-table td[data-month]').forEach(colorizeWithPulse);
  }

  function initFrequencyTable(root){
    const tables = (root || document).querySelectorAll('#frequency-table');
    tables.forEach(table=>{
      if (inited.has(table)) return;
      inited.add(table);

      table.querySelectorAll('td[data-month]').forEach(td=>{
        if (!td.textContent.trim()) td.textContent = '0';
        setValAttr(td, parseInt(td.textContent.trim(), 10) || 0);
      });

      attachEditingHandlers(table);
      observeTable(table);
      applyFrequencyColors(table);
    });
  }

  // Public helpers (optional)
  window.applyFrequencyColors = () => applyFrequencyColors();
  window.initFrequencyTable   = (root) => initFrequencyTable(root);

  // 1) Try at DOM ready (in case table is already present)
  document.addEventListener('DOMContentLoaded', () => initFrequencyTable());

  // 2) Also watch for tables added later (modal injection via innerHTML)
  new MutationObserver((muts)=>{
    for (const m of muts){
      for (const node of m.addedNodes){
        if (!(node instanceof Element)) continue;
        if (node.id === 'frequency-table' || node.querySelector?.('#frequency-table')){
          initFrequencyTable(node);
        }
      }
    }
  }).observe(document.body, { childList:true, subtree:true });

  // 3) Allow external scripts to force a refresh after bulk updates
  document.addEventListener('frequency:update', () => applyFrequencyColors());
})();
