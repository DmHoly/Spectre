/* Les autres noms d'une plaque (global `WaferLinks`) : une plaque change de nom - d'abord XX, puis YY
   après un collage. Les liens viennent de la MES (une étape entrée sous un nom, sortie sous un autre,
   enregistrés à chaque lecture de la vie en ligne) ou sont déclarés à la main ici. La page d'une
   plaque en montre la lignée (bandeau « est devenue » / « s'appelait ») ; chercher l'un des noms
   mène aux autres.

     WaferLinks.bannerHtml(plate)        le bandeau de la lignée (vide sans autre nom)
     WaferLinks.open({lasermark, onDone}) déclarer un autre nom

   Dépend de wafersApi, plateUrl (fdl.js), escapeHtml, formatDate. */

const WaferLinks = (() => {
  let dialog = null;
  let options = {};

  function nameLink(item) {
    return `<a class="mono" href="${plateUrl(item.lasermark)}">${escapeHtml(item.lasermark)}</a>`;
  }

  function how(item) {
    const parts = [item.source === "mes" ? "vu dans la MES" : "déclaré"];
    if (item.happened_at) parts.push(`le ${escapeHtml(formatDate(item.happened_at))}`);
    if (item.note) parts.push(escapeHtml(item.note));
    return parts.join(" · ");
  }

  // le bandeau : « Cette plaque est devenue YY » (le nom à suivre aujourd'hui) / « elle s'appelait XX »
  function bannerHtml(plate) {
    const chain = plate.links;
    if (!chain || (!chain.before.length && !chain.after.length)) return "";
    const out = [];
    if (chain.after.length) {
      const last = chain.after[chain.after.length - 1];
      out.push(`<div class="plate-banner plate-banner--info plate-links__banner">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>
        <span>Cette plaque a changé de nom : elle est devenue ${chain.after.map(nameLink).join(" puis ")} <span class="help" style="display:inline;margin:0;">(${how(chain.after[0])})</span>.
        Sa vie en ligne se suit aujourd'hui sous <strong>${nameLink(last)}</strong>.</span></div>`);
    }
    if (chain.before.length) {
      out.push(`<div class="plate-banner plate-banner--info plate-links__banner">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5"/><path d="m11 18-6-6 6-6"/></svg>
        <span>Avant, elle s'appelait ${chain.before.map(nameLink).join(" puis ")} <span class="help" style="display:inline;margin:0;">(${how(chain.before[chain.before.length - 1])})</span>.</span></div>`);
    }
    return out.join("");
  }

  // les noms de sa lignée, pour la case « Autres noms » de l'en-tête (avec « retirer » pour qui peut)
  function factHtml(plate, user) {
    const chain = plate.links;
    if (!chain || !chain.links.length) return "";
    return chain.links
      .map((link) => {
        const mine = user && (user.is_admin || (link.source === "manual" && link.created_by_id === user.id));
        return `<span class="plate-links__item"><a class="mono" href="${plateUrl(link.from.lasermark)}">${escapeHtml(link.from.lasermark)}</a> → <a class="mono" href="${plateUrl(link.to.lasermark)}">${escapeHtml(link.to.lasermark)}</a>
          <span class="plate-tag plate-tag--mute" title="${link.source === "mes" ? "Vu dans la MES" : `Déclaré par ${escapeHtml(link.created_by)}`}">${link.source === "mes" ? "MES" : "déclaré"}</span>${
            mine ? ` <button type="button" class="plate-links__remove" data-link="${link.id}" aria-label="Retirer le lien ${escapeHtml(link.from.lasermark)} → ${escapeHtml(link.to.lasermark)}">retirer</button>` : ""
          }</span>`;
      })
      .join("");
  }

  function build() {
    dialog = document.createElement("dialog");
    dialog.className = "wafer-dialog wafer-dialog--narrow";
    dialog.setAttribute("aria-labelledby", "wafer-link-title");
    dialog.innerHTML = `
      <form class="card-pad wafer-dialog__inner" method="dialog">
        <h2 class="wafer-dialog__title" id="wafer-link-title">Un autre nom pour cette plaque</h2>
        <p class="help wafer-dialog__lead">Une plaque qui change de nom - un collage, un report : les deux noms désignent la même plaque, chercher l'un mène à l'autre. Les changements vus dans la MES se lient d'eux-mêmes.</p>
        <div class="error" role="alert" hidden></div>
        <div class="wafer-attach">
          <fieldset class="wafer-attach__places">
            <legend>Cette plaque…</legend>
            <label class="wafer-attach__place"><input type="radio" name="wafer-link-dir" value="after" checked> <span>est devenue</span></label>
            <label class="wafer-attach__place"><input type="radio" name="wafer-link-dir" value="before"> <span>s'appelait avant</span></label>
          </fieldset>
          <label class="wafer-attach__field"><span>Lasermark</span><input class="field mono js-link-other" type="text" required maxlength="80" autocomplete="off" placeholder="YY…"></label>
          <label class="wafer-attach__field"><span>Quand <span class="help" style="display:inline;">(facultatif)</span></span><input class="field js-link-date" type="date"></label>
          <label class="wafer-attach__field"><span>Note <span class="help" style="display:inline;">(facultatif)</span></span><input class="field js-link-note" type="text" maxlength="300" placeholder="collage sur substrat CMOS…" autocomplete="off"></label>
        </div>
        <div class="wafer-dialog__actions">
          <button class="btn btn-line js-link-cancel" type="button">Annuler</button>
          <button class="btn btn-primary js-link-go" type="submit">Lier</button>
        </div>
      </form>`;
    document.body.appendChild(dialog);
    dialog.querySelector(".js-link-cancel").addEventListener("click", () => dialog.close());
    dialog.querySelector("form").addEventListener("submit", go);
  }

  async function go(event) {
    event.preventDefault();
    const other = dialog.querySelector(".js-link-other").value.trim();
    if (!other) return;
    const after = dialog.querySelector("input[name=wafer-link-dir]:checked").value === "after";
    const box = dialog.querySelector(".error");
    const button = dialog.querySelector(".js-link-go");
    button.disabled = true;
    box.hidden = true;
    try {
      await wafersApi.createLink({
        from_lasermark: after ? options.lasermark : other,
        to_lasermark: after ? other : options.lasermark,
        note: dialog.querySelector(".js-link-note").value,
        happened_at: dialog.querySelector(".js-link-date").value || null,
      });
      dialog.close();
      if (options.onDone) options.onDone();
    } catch (err) {
      box.textContent = err.message || String(err);
      box.hidden = false;
    } finally {
      button.disabled = false;
    }
  }

  function open(opts) {
    if (!dialog) build();
    options = opts || {};
    dialog.querySelector("form").reset();
    dialog.querySelector(".error").hidden = true;
    dialog.showModal();
    dialog.querySelector(".js-link-other").focus();
  }

  return { bannerHtml, factHtml, open };
})();
