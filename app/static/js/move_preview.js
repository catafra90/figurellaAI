// static/js/move_preview.js
(function () {
  // ========= CONFIG =========
  const BASE_DIR = '/static/moves';   // where .mp4/.webm/.gif live
  const CELL_SELECTOR = '.movement-cell';   // clickable element per row

  /**
   * Optional explicit map: movement name (and optional ring) -> file name
   * Keys are case-insensitive. Use 'DEFAULT' for a fallback ring.
   */
  const MOVE_MEDIA = {
    "CHEST UP": "chest_up.mp4",

    "KICKS SIDE": {
      "I": "kicks_side_I.gif",
      "DEFAULT": "kicks_side_I.gif"
    },

    "KICK SIDE TURN": {
      "I": "kick_side_turn_I.gif",
      "DEFAULT": "kick_side_turn_I.gif"
    },

    "BICEPS SEATED": {
      "I": "biceps_seated_I.gif",
      "DEFAULT": "biceps_seated_I.gif"
    },

    "ELBOW KNEES": {
      "S": "elbow_knees_S.gif",
      "DEFAULT": "elbow_knees_S.gif"
    },

    "SCISSORS": {
      "S": "scissors_S.gif",
      "DEFAULT": "scissors_S.gif"
    },

    "EAGLE": {
      "S": "eagle_S.gif",
      "DEFAULT": "eagle_S.gif",
      "caption": "Maintain hip tilted. Small motion without moving the back. Fast transition to work inner thighs."
    },

    "SWAY": {
      "-": "sway.gif",
      "DEFAULT": "sway.gif"
    },

    "STOMACH UP/DOWN": {
      "-": "stomach_up_down.gif",
      "DEFAULT": "stomach_up_down.gif"
    },

    "LEGS EXTENSION": {
      "S": "leg_extensions_S.gif",
      "DEFAULT": "leg_extensions_S.gif"
    },

    "SIDE CIRCLES": {
      "S": "side_circles_I.gif",
      "DEFAULT": "side_circles_I.gif"
    },

    "KICKS ON KNEE STR.": {
      "I": "kicks_on_knees_straight_I.gif",
      "DEFAULT": "kicks_on_knees_straight_I.gif"
    },

    "1/2 KICKS ON KNEE": {
      "I": "half_kicks_on_knees_I.gif",
      "DEFAULT": "half_kicks_on_knees_I.gif"
    },

    "ARMS BACK/UP": {
      "S": "arms_back_S.gif",
      "DEFAULT": "arms_back_S.gif"
    },

    "ARMS LIFT": {
      "S": "arms_lift_S.gif",
      "DEFAULT": "arms_lift_S.gif"
    },

    "CHEST UP ALT": {
      "-": "chest_up_alternate.gif",
      "DEFAULT": "chest_up_alternate.gif"
    },

    "ROW SEATED": {
      "I": "row_seated_I.gif",
      "DEFAULT": "row_seated_I.gif"
    },

    "SHOULDER UP": {
      "-": "shoulder_up.gif",
      "DEFAULT": "shoulder_up.gif"
    },

    "SIDE TRIANGLES": {
      "I": "side_triangles_I.gif",
      "DEFAULT": "side_triangles_I.gif"
    },

    "KNEES TO CHEST": {
      "I": "knees_to_chest_I.gif",
      "DEFAULT": "knees_to_chest_I.gif"
    },

    "CHEST UP 90": {
      "-": "chest_up_90.gif",
      "DEFAULT": "chest_up_90.gif"
    },

    "KNEES TWIST STRAIGHT": {
      "S": "knees_twist_straight_S.gif",
      "DEFAULT": "knees_twist_straight_S.gif"
    },

    "REVERSE CRUNCH": {
      "-": "reverse_crunch.gif",
      "DEFAULT": "reverse_crunch.gif"
    },

    "DOUBLE KICKS TURN": {
      "S": "double_kicks_turn_S.gif",
      "DEFAULT": "double_kicks_turn_S.gif"
    },

    "FROGGY": {
      "S": "froggy_S.gif",
      "DEFAULT": "froggy_S.gif"
    },

    "DIAGONAL KICKS": {
      "S": "diagonal_kick_S.gif",
      "DEFAULT": "diagonal_kick_S.gif"
    },

    "STOMACH TRIANGLES": {
      "-": "stomach_triangles.gif",
      "DEFAULT": "stomach_triangles.gif"
    },

    "1/2 KICK SIDE": {
      "I": "half_kick_side_I.gif",
      "DEFAULT": "half_kick_side_I.gif"
    },

    "SIDE BEND & EXTEND": {
      "I": "side_bend_extend_I.gif",
      "DEFAULT": "side_bend_extend_I.gif"
    },

    "PELVIS UP": {
      "-": "pelvis_up.gif",
      "DEFAULT": "pelvis_up.gif"
    },

    "CIRCLES ON KNEE": {
      "I": "circle_on_knees_I.gif",
      "DEFAULT": "circle_on_knees_I.gif"
    },

    "1/2 TRIANGLES O.K.": {
      "I": "half_triangles_on_knees_I.gif",
      "DEFAULT": "half_triangles_on_knees_I.gif"
    },

    "BOXING": {
      "S": "boxing_S.gif",
      "DEFAULT": "boxing_S.gif"
    },

    "SIDE ARM TURN": {
      "I": "side_arm_turn_I.gif",
      "DEFAULT": "side_arm_turn_I.gif"
    },

    "CROSSED ROW": {
      "I": "crossed_rows.gif",
      "DEFAULT": "crossed_rows.gif"
    },

    "PUSH LEGS": {
      "S": "push_legs_S.gif",
      "DEFAULT": "push_legs_S.gif"
    },

    "FROG": {
      "S": "frog_S.gif",
      "DEFAULT": "frog_S.gif"
    },

    "BICYCLE": {
      "S": "bicycle_S.gif",
      "DEFAULT": "bicycle_S.gif"
    }
  };

  // ========= Drag guard (avoid click after drag) =========
  let dragGuard = { down:false, x:0, y:0 };
  document.addEventListener('mousedown', (e)=>{ dragGuard={down:true,x:e.clientX,y:e.clientY}; }, true);
  document.addEventListener('mouseup',   ()=>{ dragGuard.down=false; }, true);

  // ========= Click handling (event delegation) =========
  document.addEventListener('click', function (e) {
    const cell = e.target.closest(CELL_SELECTOR);
    if (!cell) return;

    // Ignore if user dragged
    if (dragGuard.down) return;
    const dx = Math.abs((e.clientX||0) - (dragGuard.x||0));
    const dy = Math.abs((e.clientY||0) - (dragGuard.y||0));
    if (dx + dy > 6) return;

    const title = (cell.dataset.name || cell.textContent || '').trim();
    const ringFromData = (cell.dataset.ring || '').trim();
    const row = cell.closest('tr');
    const ringFromRow = row?.querySelector('.rings-input')?.value?.trim() || '';
    const ring = ringFromData || ringFromRow;

    // Highest priority: explicit data-file on the cell
    const explicit = (cell.dataset.file || '').trim();  // can be "kicks_side_I" or "kicks_side_I.gif"
    let resolvedPath = null;

    if (explicit) {
      resolvedPath = resolveExplicitFile(explicit);
    }

    // Next: try the mapping
    if (!resolvedPath) {
      resolvedPath = resolveFromMap(title, ring);
    }

    // Last: slugified title
    if (!resolvedPath) {
      const slug = slugify(title);
      resolvedPath = guessExisting(slug);
    }

    const sources = toSources(resolvedPath);
    openMoveVideo({ title: decorateTitle(title, ring), sources });
  });

  // ========= Helpers =========

  function decorateTitle(title, ring){
    const t = (title || 'Movement').trim();
    return (ring && ring.length) ? `${t} — ${ring}` : t;
  }

  function normalize(s){ return (s||'').trim().toUpperCase(); }

  function resolveFromMap(title, ring){
    const key = normalize(title);
    const entry = MOVE_MEDIA[key];
    if (!entry) return null;

    // Simple string: single file for all rings
    if (typeof entry === 'string') return joinBase(entry);

    // Object with ring variants
    const r = normalize(ring);
    const chosen = entry[r] || entry['DEFAULT'];
    return chosen ? joinBase(chosen) : null;
  }

  function resolveExplicitFile(nameOrWithExt){
    // Accept "slug" or "slug.ext"
    if (/\.(mp4|webm|gif)$/i.test(nameOrWithExt)) {
      return joinBase(nameOrWithExt);
    }
    // try known extensions in preferred order
    const candidates = [`${nameOrWithExt}.mp4`, `${nameOrWithExt}.webm`, `${nameOrWithExt}.gif`];
    return joinBase(candidates[0]); // we don't stat the file; we give all sources to the <video> element below
  }

  function guessExisting(slug){
    // We’ll hand all common extensions as <source> candidates; the browser will pick
    return joinBase(slug); // no extension yet; we'll expand to .mp4/.webm/.gif when building sources
  }

  function joinBase(name){
    // If name already contains '/', assume it's a path under BASE_DIR
    return name.startsWith('/') ? name : `${BASE_DIR}/${name}`;
  }

  function slugify(s){
    return (s||'').toLowerCase()
      .normalize('NFD').replace(/[\u0300-\u036f]/g,'')
      .replace(/[^a-z0-9]+/g,'_').replace(/^_+|_+$/g,'');
  }

  function toSources(resolvedPath){
    // If path includes an extension, only include that one; else include all three
    const hasExt = /\.(mp4|webm|gif)$/i.test(resolvedPath||'');
    if (hasExt) {
      const ext = resolvedPath.split('.').pop().toLowerCase();
      if (ext === 'gif') {
        return [{ src: resolvedPath, type: 'image/gif' }];
      }
      // mp4 or webm
      return [{ src: resolvedPath, type: `video/${ext}` }];
    }
    // No ext: offer all; browser picks the first it can play
    const base = resolvedPath;
    return [
      { src: `${base}.mp4`,  type: 'video/mp4'  },
      { src: `${base}.webm`, type: 'video/webm' },
      { src: `${base}.gif`,  type: 'image/gif'  },
    ];
  }

  // ========= Modal =========

  function openMoveVideo(opts){
    const { title, sources } = opts || {};
    closeExisting();

    const overlay = document.createElement('div');
    overlay.className = 'mv-overlay';
    overlay.innerHTML = `
  <div class="mv-modal" role="dialog" aria-label="${escapeHtml(title)}">
    <header class="mv-head">
      <div class="mv-title">${escapeHtml(title || 'Movement')}</div>
      <button class="mv-close" aria-label="Close">&times;</button>
    </header>
    <div class="mv-body">
      <div class="mv-video-wrap"></div>
      <div class="mv-caption" style="
          font-size:0.95rem;
          padding:0.75rem 1rem;
          background:#fff;
          border-top:1px solid #eee;
          font-weight:500;
          color:#333;">
      </div>
    </div>
  </div>
`;

    document.body.appendChild(overlay);

    // ---- inject caption text (if provided in MOVE_MEDIA) ----
    const captionEl = overlay.querySelector('.mv-caption');

    // base movement name (strip " — RING" from decorated title)
    const baseTitle = (title || '').split('—')[0].trim().toUpperCase();
    // ring, if present in the decorated title
    const ringFromTitle = (title || '').includes('—')
      ? (title.split('—')[1] || '').trim().toUpperCase()
      : '';

    const entry = MOVE_MEDIA[baseTitle];

    if (entry && typeof entry === 'object') {
      // support either a single "caption" or future per-ring captions
      const perRingCaption = entry.captions?.[ringFromTitle]; // e.g., { captions: { "S": "...", "I": "..." } }
      const caption = perRingCaption || entry.caption;

      if (caption && caption.length) {
        captionEl.textContent = caption;
      } else {
        captionEl.remove(); // no text -> remove bar
      }
    } else {
      captionEl.remove();
    }

    const wrap = overlay.querySelector('.mv-video-wrap');
    const gif = sources.find(s => s.type === 'image/gif');
    const vids = sources.filter(s => s.type.startsWith('video/'));

    if (vids.length){
      const v = document.createElement('video');
      v.setAttribute('playsinline','');
      v.setAttribute('muted','');
      v.setAttribute('loop','');
      v.setAttribute('autoplay','');
      v.setAttribute('controls','');
      vids.forEach(s => {
        const src = document.createElement('source');
        src.src = s.src; src.type = s.type;
        v.appendChild(src);
      });
      wrap.appendChild(v);
      v.muted = true;
      v.play().catch(()=>{});
    } else if (gif){
      const img = document.createElement('img');
      img.src = gif.src;
      img.alt = title || 'Movement';
      img.className = 'mv-gif';
      wrap.appendChild(img);
    } else {
      wrap.innerHTML = `<div class="mv-missing">Video not found.</div>`;
    }

    // Close actions
    overlay.addEventListener('click', (ev)=>{
      if (ev.target.classList.contains('mv-overlay') || ev.target.closest('.mv-close')) {
        closeExisting();
      }
    });

    document.addEventListener('keydown', function escClose(e){
      if (e.key === 'Escape') closeExisting();
    }, { once:true });
  }

  function closeExisting(){
    const ex = document.querySelector('.mv-overlay');
    if (ex) ex.remove();
  }

  function escapeHtml(s){
    return String(s || '').replace(/[&<>"']/g, function(m){
      return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[m];
    });
  }
})();
