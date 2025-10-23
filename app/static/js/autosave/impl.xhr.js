// Real implementation: posts to backend when you’re ready.
//(function(){
//  const DEBUG = !!window.DEBUG;

 // const XhrImpl = {
 //   enabled: true,
   // async save(card, state){
     // const { clientName, sheets } = state;
     // DEBUG && console.debug('[autosave • xhr] save ▶', clientName, sheets);
      //const res = await fetch('/charts/client/' + encodeURIComponent(clientName) + '/save', {
       // method:'POST',
       // headers:{ 'Content-Type':'application/json' },
       // body: JSON.stringify({ sheets })
     // });
     // const j = await res.json().catch(()=>({}));
     // if (!res.ok || (j.status && j.status !== 'success')) {
        throw new Error(j.message || ('HTTP '+res.status));
      //}
     // DEBUG && console.debug('[autosave • xhr] save ✓', clientName);
   // }
 // };

 // window.Autosave && window.Autosave.useImplementation(XhrImpl);
//  })();
