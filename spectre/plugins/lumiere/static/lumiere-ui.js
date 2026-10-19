/* Ce que les pages du plugin lumiere partagent (global `LumiereUI`) : l'état d'un rapport en badge, sa ligne
   dans une liste (titre, date, poids, télécharger / retirer), et le suivi d'un rapport en cours - une relecture
   toutes les 2 s tant qu'il n'est ni fait ni en échec (LumiereUI.follow(id, onChange) -> stop()).
   Dépend de lumiereApi, escapeHtml, formatDate, timeAgo. */

const LumiereUI = (() => {
  const POLL_MS = 2000;
  const STATUS = {
    queued: { label: "en attente", badge: "badge-draft" },
    running: { label: "en cours", badge: "badge-running" },
    done: { label: "prêt", badge: "badge-concluded" },
    error: { label: "en échec", badge: "badge-hold" },
  };

  function badge(status) {
    const s = STATUS[status] || { label: status, badge: "badge-draft" };
    return `<span class="badge ${s.badge}"><span class="dot" aria-hidden="true"></span>${escapeHtml(s.label)}</span>`;
  }

  function weight(bytes) {
    if (!bytes) return "";
    return bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} Mo` : `${Math.round(bytes / 1024)} Ko`;
  }

  // une ligne de rapport : {report, context: afficher le contexte (la plaque) ?}
  function rowHtml(report, { context = true } = {}) {
    const busy = report.status === "queued" || report.status === "running";
    const when = report.finished_at || report.created_at;
    return `<li class="lm-report${busy ? " is-busy" : ""}" data-report="${report.id}">
      <div class="lm-report__main">
        <div class="lm-report__title">${escapeHtml(context ? report.title : report.title.split(" · ")[0])} ${badge(report.status)}</div>
        <div class="lm-report__meta">${escapeHtml(formatDate(when))} · ${escapeHtml(timeAgo(when))}${report.bytes ? ` · ${weight(report.bytes)}` : ""}${report.message ? ` · <span class="lm-report__message">${escapeHtml(report.message)}</span>` : ""}</div>
      </div>
      <div class="lm-report__actions">
        ${report.status === "done" ? `<a class="btn btn-primary" href="${escapeHtml(lumiereApi.fileUrl(report.id))}" download title="Télécharger le rapport HTML (il s'ouvre hors ligne)">Télécharger</a>` : ""}
        ${busy ? `<span class="skeleton lm-report__wait" aria-label="Génération en cours"></span>` : `<button type="button" class="btn btn-line" data-remove="${report.id}" title="Retirer ce rapport du serveur">Retirer</button>`}
      </div>
    </li>`;
  }

  // relit le rapport jusqu'à ce qu'il soit fait ou en échec ; rend une fonction qui arrête le suivi
  function follow(id, onChange) {
    let timer = null;
    let stopped = false;
    async function tick() {
      if (stopped) return;
      try {
        const report = await lumiereApi.get(id);
        onChange(report);
        if (report.status === "queued" || report.status === "running") timer = setTimeout(tick, POLL_MS);
      } catch (err) {
        onChange({ id, status: "error", message: err.message || String(err), title: "" });
      }
    }
    timer = setTimeout(tick, POLL_MS);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }

  return { badge, rowHtml, follow, weight, STATUS };
})();
