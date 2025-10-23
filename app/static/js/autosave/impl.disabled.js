// Disabled implementation: keeps UX & flag mirroring, but DOES NOT persist.
(function(){
  const DEBUG = !!window.DEBUG;

  const DisabledImpl = {
    enabled: false,
    save(card, state){
      // No network. Just log so you can verify collectors/state.
      DEBUG && console.debug('[autosave • disabled] would-save snapshot →', state.clientName, state.sheets);
      // You could also stash in memory/localStorage here if you want ephemeral “feel”.
    },
    afterAttach(card){
      // Optional: disable explicit save buttons to avoid confusion.
      try {
        card.querySelectorAll('[data-action="save"], .js-save, button.save').forEach(btn=>{
          btn.disabled = true;
          btn.title = "Saving is disabled in this build.";
        });
      } catch(_) {}
    },
    afterDetach(){ /* noop */ }
  };

  window.Autosave && window.Autosave.useImplementation(DisabledImpl);
})();
