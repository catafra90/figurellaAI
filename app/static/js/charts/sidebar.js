// static/js/charts/sidebar.js
(function(){
  const sidebar   = document.getElementById('client-sidebar');
  if (!sidebar) return;

  const toggleBtn = document.getElementById('sidebar-toggle');
  const resizer   = document.getElementById('sidebar-resizer');
  const stateKey  = 'charts.sidebar.state';
  const widthKey  = 'charts.sidebar.width';

  // Restore state & width
  const savedState = localStorage.getItem(stateKey);
  if (savedState) sidebar.setAttribute('data-state', savedState);

  const savedWidth = localStorage.getItem(widthKey);
  if (savedWidth) {
    document.documentElement.style.setProperty('--sidebar-width', savedWidth);
  }

  function setState(next){
    sidebar.setAttribute('data-state', next);
    localStorage.setItem(stateKey, next);
  }

  // Toggle: desktop collapses; mobile hides off-canvas
  toggleBtn && toggleBtn.addEventListener('click', () => {
    const isMobile = window.matchMedia('(max-width: 900px)').matches;
    const cur = sidebar.getAttribute('data-state') || 'expanded';
    let next;
    if (isMobile) {
      next = (cur === 'hidden') ? 'expanded' : 'hidden';
    } else {
      next = (cur === 'collapsed') ? 'expanded' : 'collapsed';
    }
    setState(next);
  });

  // Resize: drag handle horizontally
  let dragging = false;
  let startX = 0;
  let startWidth = 0;

  const onMove = (e) => {
    if (!dragging) return;
    const pageX = e.touches ? e.touches[0].pageX : e.pageX;
    const delta = pageX - startX;
    const next = Math.min(520, Math.max(220, startWidth + delta));
    document.documentElement.style.setProperty('--sidebar-width', `${next}px`);
  };

  const onUp = () => {
    if (!dragging) return;
    dragging = false;
    document.body.style.userSelect = '';
    const val = getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width').trim();
    localStorage.setItem(widthKey, val);
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('touchmove', onMove);
    window.removeEventListener('mouseup', onUp);
    window.removeEventListener('touchend', onUp);
  };

  resizer && resizer.addEventListener('mousedown', (e) => {
    if ((sidebar.getAttribute('data-state') || 'expanded') !== 'expanded') return;
    dragging = true;
    startX = e.pageX;
    startWidth = parseInt(getComputedStyle(sidebar).width, 10);
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  });

  resizer && resizer.addEventListener('touchstart', (e) => {
    if ((sidebar.getAttribute('data-state') || 'expanded') !== 'expanded') return;
    dragging = true;
    startX = e.touches[0].pageX;
    startWidth = parseInt(getComputedStyle(sidebar).width, 10);
    document.body.style.userSelect = 'none';
    window.addEventListener('touchmove', onMove, {passive:false});
    window.addEventListener('touchend', onUp);
  });

  // Optional: keyboard shortcut (Shift+S) to toggle
  window.addEventListener('keydown', (e) => {
    if (e.shiftKey && (e.key === 'S' || e.key === 's')) {
      toggleBtn && toggleBtn.click();
    }
  });
})();
