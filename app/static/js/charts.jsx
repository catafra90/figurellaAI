/* charts.jsx (delegates to unified modal system) */
const { useEffect, useRef } = React;

export default function ClientChartModal({ client, onClose }) {
  const modalRef = useRef(null);

  useEffect(() => {
    // Open/focus the unified vanilla modal
    const el =
      (window.ClientModal?.open && window.ClientModal.open({ title: client })) ||
      (window.openClientChartByName && window.openClientChartByName(client, { mode: "default" })) ||
      null;

    modalRef.current = el;

    // Load chart HTML into the modal body
    if (el) {
      const bodyEl = el.querySelector(".modal-body");
      if (bodyEl) {
        bodyEl.innerHTML = "<p>Loading…</p>";
        fetch(`/charts/client/${encodeURIComponent(client)}`)
          .then((r) => r.text())
          .then((html) => {
            bodyEl.innerHTML = html || "<div>No data available.</div>";
            document.dispatchEvent(new CustomEvent("clientmodal:recenter", { detail: { el } }));
          })
          .catch(() => {
            bodyEl.innerHTML = '<p class="text-red-600">Failed to load chart.</p>';
          });
      }
    }

    // Bubble close back to React when the unified modal closes
    const onClosed = (e) => {
      if (e.detail?.el === modalRef.current) onClose?.();
    };
    document.addEventListener("clientmodal:closed", onClosed);

    return () => {
      document.removeEventListener("clientmodal:closed", onClosed);
      if (modalRef.current?.isConnected) {
        modalRef.current.querySelector(".modal-close")?.click();
      }
      modalRef.current = null;
    };
  }, [client, onClose]);

  return null; // no separate window here
}
