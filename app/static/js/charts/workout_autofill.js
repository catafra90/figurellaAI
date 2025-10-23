/* Workout autofill (uses blocks.py data, with GK fallback to legacy globals)
 * Type select: #workout-rev1-type OR #workout-type OR [name="workout_type"]/[name="type"]/data-workout-type
 * Program table: headers contain "Movements" and "Rings"
 * GK section: #gk-rev1-section and #gk-rev1-table
 */
(function () {
  const DEBUG = false;
  const log = (...a) => { if (DEBUG) console.log('[workout_autofill]', ...a); };

  // ---------- DOM finders ----------
  function findTypeSelect(root=document){
    return root.querySelector(
      '#workout-rev1-type, #workout-type, select[name="workout_type"], select[name="type"], select[data-workout-type]'
    );
  }
  function findWorkoutTable(root=document){
    const tables = Array.from(root.querySelectorAll('table'));
    for (const t of tables) {
      const headers = Array.from(t.querySelectorAll('thead th, thead td'))
        .map(th => (th.textContent || '').trim().toLowerCase());
      if (headers.includes('movements') && headers.includes('rings')) return t;
    }
    return null;
  }
  function findGK() {
    const sec  = document.getElementById('gk-rev1-section');
    const tbl  = document.getElementById('gk-rev1-table');
    const body = tbl?.tBodies?.[0] || null;
    return {sec, tbl, body};
  }

  // ---------- Data sources ----------
  function mapFromInline(){
    if (window.WORKOUT_BLOCKS && typeof window.WORKOUT_BLOCKS === 'object') return window.WORKOUT_BLOCKS;
    const tag = document.getElementById('workout-blocks-json');
    if (!tag) return null;
    try { return JSON.parse(tag.textContent || '{}'); } catch { return null; }
  }
  async function fetchMap(){
    try {
      const r = await fetch('/charts/workout/blocks.json', { credentials:'same-origin' });
      if (!r.ok) return null;
      const j = await r.json();
      if (j && typeof j === 'object') return j;
    } catch {}
    return null;
  }
  async function fetchBlock(key){
    try {
      const r = await fetch('/charts/workout/blocks.json?key=' + encodeURIComponent(key), { credentials:'same-origin' });
      if (!r.ok) return null;
      const j = await r.json();
      if (j && (Array.isArray(j.rows) || Array.isArray(j.GK))) return j;
    } catch {}
    return null;
  }
  async function loadMap(){
    const inline = mapFromInline();
    if (inline) { log('Using inline blocks map'); return inline; }
    const all = await fetchMap();
    if (all) { log('Using /charts/workout/blocks.json'); return all; }
    log('No blocks map found; will fetch per key.');
    return null;
  }

  // ---------- Legacy GK globals fallback ----------
  function legacyGKFor(key){
    const defs  = (window.GK_DEFAULTS && window.GK_DEFAULTS[key]) || [];
    const rings = (window.GK_RINGS_DEFAULTS && window.GK_RINGS_DEFAULTS[key]) || [];
    if (!defs || !defs.length) return [];
    return defs.map((d,i)=>{
      if (typeof d === 'string') return {Workout:d, Rings:(rings[i]||''), Notes:''};
      if (d && typeof d === 'object') return {Workout:d.Workout||d.w||'', Rings:d.Rings||d.r||'', Notes:d.Notes||d.n||''};
      return {Workout:'',Rings:'',Notes:''};
    });
  }

  // ---------- Cell helpers ----------
  const tdInput = (td)=> td?.querySelector('input, textarea') || null;
  function writeCell(td, val){
    const inp = tdInput(td);
    if (inp) { inp.value = val || ''; inp.dispatchEvent(new Event('input',{bubbles:true})); return; }
    if (td?.hasAttribute('contenteditable')) { td.textContent = val || ''; return; }
    if (td) td.textContent = val || '';
  }
  function isEmpty(td){
    const inp = tdInput(td);
    if (inp) return !String(inp.value||'').trim();
    return !String(td?.textContent||'').trim();
  }
  function pulse(tr){
    tr?.classList?.add('prefill-pulse');
    setTimeout(()=> tr?.classList?.remove('prefill-pulse'), 800);
  }
  function rowCells(tr){
    const tds = tr.querySelectorAll('td, th');
    return { mov: tds[1] || null, rings: tds[2] || null, notes: tds[3] || null };
  }

  // ---------- GK section ----------
  function shouldShowGK(key, gk){
    return /^TO|^B/i.test(key) || (Array.isArray(gk) && gk.length > 0);
  }
  function fillGKRows(gkRows){
    const {sec, body} = findGK();
    if (!sec || !body) return;
    const trs = Array.from(body.rows);
    for (let i=0; i<trs.length; i++){
      const spec = gkRows[i] || {Workout:'', Rings:'', Notes:''};
      const w = trs[i].querySelector('.rev1-gk-workout');
      const r = trs[i].querySelector('.rev1-gk-rings');
      const n = trs[i].querySelector('.rev1-gk-notes');
      if (w) w.value = spec.Workout || '';
      if (r) r.value = spec.Rings   || '';
      if (n && !n.value) n.value = spec.Notes || ''; // only fill notes if empty
      pulse(trs[i]);
    }
  }
  function toggleGK(show){
    const {sec} = findGK();
    if (!sec) return;
    if (show) { sec.classList.remove('hidden'); sec.style.removeProperty('display'); }
    else      { sec.classList.add('hidden');    sec.style.setProperty('display','none','important'); }
  }

  // ---------- Main ----------
  async function getSpecForKey(key, map){
    if (!key) return {rows:[], GK:[]};
    if (map && map[key]) return {rows:(map[key].rows||[]), GK:(map[key].GK||[])};
    const blk = await fetchBlock(key);
    if (blk) return {rows:(blk.rows||[]), GK:(blk.GK||[])};
    return {rows:[], GK:[]};
  }

  async function applyAutofill({root=document, overwrite=false}={}){
    const select = findTypeSelect(root);
    const table  = findWorkoutTable(root);
    if (!select || !table) { log('select or table not found'); return; }

    const key = (select.value || select.options?.[select.selectedIndex]?.value || '').trim();
    if (!key) return;

    const map  = await loadMap();
    let {rows, GK} = await getSpecForKey(key, map);

    // If GK missing in blocks, fallback to legacy globals
    if (!GK || !GK.length) {
      const legacy = legacyGKFor(key);
      if (legacy.length) GK = legacy;
    }

    // Fill program table
    if (rows && rows.length){
      const trs = Array.from(table.tBodies[0].rows);
      for (let i=0; i<trs.length; i++){
        const spec = rows[i] || {Workout:'',Rings:'',Notes:''};
        const {mov, rings, notes} = rowCells(trs[i]);
        if (!mov || !rings || !notes) continue;
        const doW = overwrite || isEmpty(mov);
        const doR = overwrite || isEmpty(rings);
        const doN = overwrite || isEmpty(notes);
        if (doW) writeCell(mov,   spec.Workout||'');
        if (doR) writeCell(rings, spec.Rings  ||'');
        if (doN) writeCell(notes, spec.Notes  ||'');
        if (doW || doR || doN) pulse(trs[i]);
      }
    }

    // GK show + fill
    const showGK = shouldShowGK(key, GK);
    toggleGK(showGK);
    if (showGK && Array.isArray(GK) && GK.length) fillGKRows(GK);
  }

  function wire(root=document){
    const select = findTypeSelect(root);
    const table  = findWorkoutTable(root);
    if (!select || !table) return;

    select.addEventListener('change', (e) => {
      const overwrite = !!(e && (e.altKey || (e.detail && e.detail.overwrite)));
      applyAutofill({root, overwrite});
    });

    if (select.value) applyAutofill({root, overwrite:false});
  }

  function ready(fn){
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, {once:true});
    else fn();
  }

  ready(() => {
    wire(document);
    const obs = new MutationObserver((muts) => {
      for (const m of muts) {
        for (const node of m.addedNodes) {
          if (!(node instanceof Element)) continue;
          if (findTypeSelect(node) && findWorkoutTable(node)) wire(node);
          node.querySelectorAll?.('select, table').forEach(() => {
            if (findTypeSelect(node) && findWorkoutTable(node)) wire(node);
          });
        }
      }
    });
    obs.observe(document.documentElement, {childList:true, subtree:true});
  });

  window.WorkoutAutofill = {
    apply: (opts) => applyAutofill(opts),
    wire:  (root) => wire(root),
  };
})();
