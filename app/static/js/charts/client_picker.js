// static/js/charts/client_picker.js — header Status dropdown (polished)
(function () {
  let allClients = [];
  let loaded = false;

  const qs  = (sel, root=document) => root.querySelector(sel);
  const qsa = (sel, root=document) => Array.from(root.querySelectorAll(sel));
  function debounce(fn, ms=120){ let t; return (...a)=>{ clearTimeout(t); t=setTimeout(()=>fn(...a), ms); }; }
  function esc(s){ return (s ?? '').toString().replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])); }

  function getKey(obj, names) {
    if (!obj) return undefined;
    const lower = Object.create(null);
    for (const k of Object.keys(obj)) lower[k.toLowerCase()] = k;
    for (const n of names) {
      const k = lower[n.toLowerCase()];
      if (k !== undefined) return obj[k];
    }
    return undefined;
  }
  function fromExcelSerial(num) {
    if (typeof num !== 'number' || !isFinite(num)) return null;
    const epoch = new Date(Date.UTC(1899, 11, 30));
    const ms = Math.round(num * 86400000);
    return new Date(epoch.getTime() + ms);
  }
  function fmtDate(val) {
    if (val == null || val === '') return '';
    if (typeof val === 'number') {
      const d = fromExcelSerial(val);
      if (d && !isNaN(d)) {
        const mm = String(d.getUTCMonth()+1).padStart(2,'0');
        const dd = String(d.getUTCDate()).padStart(2,'0');
        const yy = d.getUTCFullYear();
        return `${mm}/${dd}/${yy}`;
      }
      return '';
    }
    const d = new Date(val);
    if (isNaN(d)) return '';
    const mm = String(d.getMonth()+1).padStart(2,'0');
    const dd = String(d.getDate()).padStart(2,'0');
    const yy = d.getFullYear();
    return `${mm}/${dd}/${yy}`;
  }
  function splitName(raw) {
    const s = (raw || '').trim();
    if (!s) return { first:'', last:'' };
    if (s.includes(',')) { const [last, rest] = s.split(',', 2); const first = (rest || '').trim().split(/\s+/)[0] || ''; return { first, last: last.trim() }; }
    const parts = s.split(/\s+/);
    if (parts.length === 1) return { first: parts[0], last: '' };
    return { first: parts.slice(0, -1).join(' '), last: parts[parts.length - 1] };
  }

  const STATUS_OPTIONS = [
    { value: 'all',       label: 'All statuses' },
    { value: 'current',   label: 'Current client' },
    { value: 'no show',   label: 'No Show' },
    { value: 'flop',      label: 'Flop' },
    { value: 'expired',   label: 'Expired' },
    { value: 'try',       label: 'Try' },
    { value: 'scheduled', label: 'Scheduled' },
  ];
  function normalizeStatus(s){
    const t = (s || '').toString().trim().toLowerCase().replace(/_/g,' ').replace(/\s+/g,' ');
    if (!t) return '';
    if (t.includes('current'))   return 'current';
    if (t.includes('no show'))   return 'no show';
    if (t.includes('flop'))      return 'flop';
    if (t.includes('expired'))   return 'expired';
    if (/\btry\b/.test(t))       return 'try';
    if (t.includes('sched'))     return 'scheduled';
    return t;
  }
  let selectedStatus = 'all';

  function detectRegKey(sampleObj){
    if (!sampleObj) return null;
    const prio = ['registrationDate','registered_at','registeredAt','createdAt','created_on','created','addedAt','added_at','joined_at','reg_date','dateAdded'];
    const lower = Object.create(null);
    for (const k of Object.keys(sampleObj)) lower[k.toLowerCase()] = k;
    for (const p of prio) { const hit = lower[p.toLowerCase()]; if (hit) return hit; }
    for (const k of Object.keys(sampleObj)) {
      const v = sampleObj[k];
      if ((typeof v === 'string' && /\d{4}-\d{2}-\d{2}/.test(v)) && /(reg|creat|add|join)/i.test(k)) return k;
      if (typeof v === 'number' && /(reg|creat|add|join)/i.test(k)) return k;
    }
    return null;
  }

  async function fetchClients() {
    if (loaded && allClients.length) return;
    const res  = await fetch('/charts/clients.json', { cache: 'no-store' });
    const json = await res.json();
    const raw  = json.clients || [];

    const regKeyDetected = detectRegKey(raw[0]);

    allClients = raw.map(c => {
      const firstExplicit = getKey(c, ['name','firstName','first_name']);
      const lastExplicit  = getKey(c, ['surname','lastName','last_name']);
      const fullName = getKey(c, ['fullName', 'full_name']) || '';
      const inferred = splitName(fullName);
      const f = (firstExplicit || inferred.first || '').trim();
      const l = (lastExplicit  || inferred.last  || '').trim();

      const regVal = (regKeyDetected ? c[regKeyDetected] : undefined);
      const regIso = regVal !== undefined ? regVal : (getKey(c, ['registrationDate','registered_at','registeredAt','createdAt','addedAt','dateAdded']) || '');

      const statusRaw = (getKey(c, ['status','statusString']) || '').toString().trim();

      return {
        __first: f,
        __last:  l,
        __full:  (f || l) ? `${f} ${l}`.trim() : (fullName || '').trim(),
        __reg:   regIso,
        __status: statusRaw,
        __status_norm: normalizeStatus(statusRaw),
      };
    });

    allClients.sort((a,b) => {
      const la=a.__last.toLowerCase(), lb=b.__last.toLowerCase();
      if (la !== lb) return la.localeCompare(lb);
      return a.__first.toLowerCase().localeCompare(b.__first.toLowerCase());
    });

    loaded = true;
  }

  // ---------- Dropdown styles (injected once) ----------
  function ensureDDStyles(){
    if (qs('#client-picker-dd-styles')) return;
    const style = document.createElement('style');
    style.id = 'client-picker-dd-styles';
    style.textContent = `
      .status-dd-menu {
        position: fixed;
        z-index: 99999;
        min-width: 12rem;
        background: #ffffff;
        color: #0f172a;            /* slate-900 */
        border: 1px solid #e2e8f0; /* slate-200 */
        border-radius: 0.75rem;    /* rounded-xl */
        box-shadow: 0 8px 24px rgba(2,6,23,.18), 0 2px 8px rgba(2,6,23,.08);
        overflow: hidden;
      }
      .status-dd-item {
        display: block;
        width: 100%;
        text-align: left;
        padding: .5rem .75rem;
        font-size: .925rem;
        line-height: 1.25rem;
        background: #ffffff;
        border: 0;
        cursor: pointer;
      }
      .status-dd-item:hover { background: #f1f5f9; }        /* slate-100 */
      .status-dd-item[aria-selected="true"] { 
        background: #eef2ff;                                /* indigo-50 */
        font-weight: 600;
      }
      .status-dd-sep { height:1px; background:#e2e8f0; margin:.25rem 0; }
    `;
    document.head.appendChild(style);
  }

  // ---------- Dropdown portal ----------
  function ensurePortal() {
    let p = qs('#status-dd-portal');
    if (!p) {
      ensureDDStyles();
      p = document.createElement('div');
      p.id = 'status-dd-portal';
      p.className = 'status-dd-menu';
      p.style.display = 'none';
      document.body.appendChild(p);
    }
    return p;
  }

  function statusLabelFromValue(v){
    const f = STATUS_OPTIONS.find(o => o.value === v);
    return f ? f.label : 'All statuses';
  }

  function buildMenuHtml(){
    return STATUS_OPTIONS.map(o =>
      `<button type="button" data-status="${esc(o.value)}"
               class="status-dd-item"
               ${o.value === selectedStatus ? 'aria-selected="true"' : ''}>
         ${esc(o.label)}
       </button>`
    ).join('');
  }

  function openMenuForAnchor(btn) {
    const portal = ensurePortal();
    portal.innerHTML = buildMenuHtml();

    // Position (align right under header cell, with viewport clamping)
    const rect = btn.getBoundingClientRect();
    const menuWidth = 200; // ~12rem
    let left = Math.round(rect.right - menuWidth);
    const top  = Math.round(rect.bottom + 6);
    left = Math.max(8, Math.min(left, window.innerWidth - menuWidth - 8));
    portal.style.left = left + 'px';
    portal.style.top  = top + 'px';
    portal.style.display = 'block';

    const onDocClick = (e) => { if (e.target === btn) return; if (!portal.contains(e.target)) closeMenu(); };
    const onEsc = (e) => { if (e.key === 'Escape') closeMenu(); };
    const onResize = () => closeMenu();

    function closeMenu() {
      portal.style.display = 'none';
      document.removeEventListener('click', onDocClick, true);
      window.removeEventListener('keydown', onEsc, true);
      window.removeEventListener('resize', onResize, true);
      window.removeEventListener('scroll', onResize, true);
    }

    qsa('[data-status]', portal).forEach(el=>{
      el.addEventListener('click', (ev)=>{
        const v = ev.currentTarget.getAttribute('data-status') || 'all';
        selectedStatus = v;
        const lab = qs('#status-dd-label');
        if (lab) lab.textContent = statusLabelFromValue(v);
        closeMenu();
        applyFiltersAndRender();
      });
    });

    document.addEventListener('click', onDocClick, true);
    window.addEventListener('keydown', onEsc, true);
    window.addEventListener('resize', onResize, true);
    window.addEventListener('scroll', onResize, true);
  }

  // ---------- Table header ----------
  function patchHeader() {
    const thead = qs('#client-picker-head'); if (!thead) return;
    thead.innerHTML = `
      <tr>
        <th class="text-left py-2 border-b">Name</th>
        <th class="text-left py-2 border-b">Surname</th>
        <th class="text-left py-2 border-b">Registration</th>
        <th class="text-left py-2 border-b">
          <button id="status-dd-btn" type="button"
                  class="inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-slate-50">
            <span>Status:</span>
            <span id="status-dd-label" class="font-medium">${esc(statusLabelFromValue(selectedStatus))}</span>
            <span aria-hidden="true">▾</span>
          </button>
        </th>
      </tr>
    `;
    const btn  = qs('#status-dd-btn', thead);
    btn.addEventListener('click', (e)=> { e.preventDefault(); e.stopPropagation(); openMenuForAnchor(btn); });
  }

  function filterList() {
    const input = qs('#client-picker-search');
    const q = (input?.value || '').trim().toLowerCase();
    const wantAll = (selectedStatus === 'all');
    return allClients.filter(c => {
      if (!wantAll && c.__status_norm !== selectedStatus) return false;
      if (!q) return true;
      const reg = fmtDate(c.__reg).toLowerCase();
      return (
        c.__first.toLowerCase().includes(q) ||
        c.__last.toLowerCase().includes(q)  ||
        (c.__full || '').toLowerCase().includes(q) ||
        reg.includes(q)
      );
    });
  }

  function render(list) {
    const tbody = qs('#client-picker-body'); if (!tbody) return;
    patchHeader();
    tbody.innerHTML = '';
    const frag = document.createDocumentFragment();
    list.forEach(c => {
      const tr = document.createElement('tr');
      tr.className = 'hover:bg-slate-50 cursor-pointer';
      tr.innerHTML = `
        <td class="py-2 border-b">${esc(c.__first)}</td>
        <td class="py-2 border-b">${esc(c.__last)}</td>
        <td class="py-2 border-b">${esc(fmtDate(c.__reg))}</td>
        <td class="py-2 border-b">${esc(c.__status)}</td>
      `;
      tr.addEventListener('click', () => {
        const title = c.__full || c.__first || '';
        if (title && typeof window.openClientChartByName === 'function') {
          window.openClientChartByName(title, { mode: 'xl' });
        }
        closePicker();
      });
      frag.appendChild(tr);
    });
    tbody.appendChild(frag);
  }

  function applyFiltersAndRender(){ render(filterList()); }

  function openPicker() {
    const picker = qs('#client-picker'); if (!picker) return;
    picker.classList.remove('hidden');
    const input = qs('#client-picker-search');
    if (input) { input.value=''; input.focus(); }
    applyFiltersAndRender();

    picker.__onEsc = (ev)=>{ if (ev.key==='Escape') closePicker(); };
    window.addEventListener('keydown', picker.__onEsc, { passive:true });
    picker.__onClickOutside = (ev)=>{
      const card = qs('.client-picker-card', picker) || qs('[data-client-picker-card]', picker);
      if (!card) return;
      if (!card.contains(ev.target)) closePicker();
    };
    picker.addEventListener('mousedown', picker.__onClickOutside);
  }
  function closePicker() {
    const picker = qs('#client-picker'); if (!picker) return;
    picker.classList.add('hidden');
    if (picker.__onEsc) { window.removeEventListener('keydown', picker.__onEsc); picker.__onEsc=null; }
    if (picker.__onClickOutside) { picker.removeEventListener('mousedown', picker.__onClickOutside); picker.__onClickOutside=null; }
  }
  function togglePicker() {
    const picker = qs('#client-picker'); if (!picker) return;
    picker.classList.contains('hidden') ? openPicker() : closePicker();
  }

  function setupSearch() {
    const input = qs('#client-picker-search'); if (!input) return;
    const onSearch = debounce(applyFiltersAndRender, 120);
    input.addEventListener('input', onSearch);
  }
  function setupDelegates() {
    document.addEventListener('click', (e) => {
      const btn = e.target?.closest?.('[data-open-client-picker]');
      if (!btn) return;
      e.preventDefault();
      handleOpenButton();
    });
    document.addEventListener('click', (e) => {
      const dim = e.target?.closest?.('[data-dismiss="picker"]');
      if (dim) closePicker();
    });
  }
  async function handleOpenButton() {
    try { await fetchClients(); togglePicker(); }
    catch (err) { console.error('[client_picker] load failed:', err); alert('Could not load clients.'); }
  }

  function init(){ setupDelegates(); setupSearch(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
