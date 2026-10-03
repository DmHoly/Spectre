/* Les preuves d'une expérience, panneau de sa fiche (ExperiencePage.registerPanel, onglet
   « Données ») : chaque preuve (description, liens, mesure, objectif visé, interprétation, images
   annotées d'une flèche ou d'un cadre), la comparaison de deux preuves, et le formulaire d'ajout
   (liens, images collées, mesure, étape associée). Les anciennes preuves « graphique » se lisent
   (titre, axes, requête) ; on n'en crée plus. Les preuves de la version affichée se lisent par
   evidenceApi.list (le détail de l'étude n'en donne que le nombre) ; écritures : evidenceApi, avec
   la version affichée. */

(() => {
  const EVIDENCE_KIND_LABELS = { image: "Image", graph: "Graphique" };

  function stepLabel(ctx, index) {
    const step = ctx.process?.steps?.[index];
    // une étape que le procédé actuel n'a plus (une évolution a raccourci la liste) : introuvable
    return step ? ExperimentVocabulary.stepLabel(step) : `étape #${index + 1} (introuvable)`;
  }

  // Les annotations (flèche / cadre) d'une image, en % de l'image : le viewBox 0..100 sans ratio
  // imposé les reprojette sur l'image affichée, quel que soit son format.
  function annotationMarkersSvg(annotations) {
    const shapes = (annotations || [])
      .map((a) => {
        if (a.type === "arrow") {
          return `<line x1="${a.x}" y1="${a.y}" x2="${a.x2}" y2="${a.y2}" stroke="var(--accent)" stroke-width="0.8" vector-effect="non-scaling-stroke" marker-end="url(#annotation-arrowhead)"/>`;
        }
        const x = Math.min(a.x, a.x2);
        const y = Math.min(a.y, a.y2);
        return `<rect x="${x}" y="${y}" width="${Math.abs(a.x2 - a.x)}" height="${Math.abs(a.y2 - a.y)}" fill="var(--accent)" fill-opacity="0.18" stroke="var(--accent)" stroke-width="0.8" vector-effect="non-scaling-stroke"/>`;
      })
      .join("");
    return `
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" style="position:absolute;inset:0;width:100%;height:100%;">
        <defs>
          <marker id="annotation-arrowhead" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto" viewBox="0 0 8 6">
            <path d="M0,0 L8,3 L0,6 z" fill="var(--accent)"/>
          </marker>
        </defs>
        ${shapes}
      </svg>`;
  }

  // Les images d'une preuve, chacune avec ses annotations.
  function imagesHtml(ctx, e) {
    const { images } = e;
    if (!images.length) return e.kind === "image" ? `<div class="help" style="margin-top:8px;">Image en cours d'envoi ou absente.</div>` : "";
    const all = e.annotations;
    return `<div class="evidence-images" data-count="${Math.min(images.length, 3)}">${images
      .map((attachment) => {
        const mine = all.map((a, i) => ({ ...a, globalIndex: i })).filter((a) => !a.attachment_id || a.attachment_id === attachment.id);
        const list = mine
          .map(
            (a) => `
            <div style="display:flex;justify-content:space-between;align-items:center;font-size:11.5px;padding:3px 0;">
              <span>${a.type === "arrow" ? "Flèche" : "Cadre"}${a.label ? " — " + escapeHtml(a.label) : ""}</span>
              ${
                ctx.canEdit
                  ? `<button type="button" class="js-remove-annotation" data-evidence-id="${escapeHtml(e.id)}" data-index="${a.globalIndex}" data-report-hide aria-label="Retirer l'annotation" style="background:none;border:none;cursor:pointer;color:var(--text-faint);font-size:14px;line-height:1;">&times;</button>`
                  : ""
              }
            </div>`
          )
          .join("");
        return `
        <figure class="evidence-image">
          <div class="js-annotation-image" data-evidence-id="${escapeHtml(e.id)}" data-attachment-id="${escapeHtml(attachment.id)}" style="position:relative;display:inline-block;max-width:100%;cursor:${ctx.canEdit ? "crosshair" : "default"};">
            <img src="${escapeHtml(attachment.url)}" alt="${escapeHtml(attachment.caption || attachment.filename || "Image de la preuve")}" style="max-width:100%;display:block;border-radius:var(--radius-sm);">
            ${annotationMarkersSvg(mine)}
          </div>
          ${attachment.caption ? `<figcaption class="evidence-image__caption">${escapeHtml(attachment.caption)}</figcaption>` : ""}
          ${list ? `<div style="margin-top:4px;">${list}</div>` : ""}
          ${
            ctx.canEdit
              ? `<div class="js-annotation-tools" data-attachment-id="${escapeHtml(attachment.id)}" data-report-hide style="margin-top:6px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;">
                  <button type="button" class="btn btn-line js-annotation-tool" data-tool="arrow" style="min-height:30px;padding:3px 9px;font-size:11.5px;">Flèche</button>
                  <button type="button" class="btn btn-line js-annotation-tool" data-tool="box" style="min-height:30px;padding:3px 9px;font-size:11.5px;">Cadre</button>
                  <button type="button" class="btn btn-primary js-annotation-save" style="min-height:30px;padding:3px 9px;font-size:11.5px;">Enregistrer les annotations</button>
                  <span class="help js-annotation-hint" style="margin:0;"></span>
                </div>`
              : ""
          }
        </figure>`;
      })
      .join("")}</div>`;
  }

  // Un lien de preuve : une adresse web s'ouvre dans un onglet ; un chemin réseau ou disque
  // (\\serveur\partage\..., S:\...), que le navigateur refuse d'ouvrir, se copie.
  const LINK_ICONS = {
    folder: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>`,
    slides: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M12 16v4M8 20h8"/><path d="M7 12l3-3 2 2 4-4"/></svg>`,
    file: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg>`,
    web: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/></svg>`,
  };

  function describeLink(link) {
    const isWeb = /^https?:\/\//i.test(link);
    let tail = link.replace(/[\\/]+$/, "");
    if (isWeb) {
      try {
        const u = new URL(link);
        tail = decodeURIComponent(u.pathname.replace(/\/+$/, "").split("/").pop() || u.hostname);
      } catch (e) {
        tail = link;
      }
    } else {
      tail = tail.split(/[\\/]/).pop() || link;
    }
    const ext = ((tail.match(/\.([a-z0-9]{2,5})$/i) || [])[1] || "").toLowerCase();
    let kind = "file";
    let label = "Fichier";
    if (["ppt", "pptx", "pptm", "odp"].includes(ext)) [kind, label] = ["slides", "Présentation"];
    else if (!ext) [kind, label] = isWeb ? ["web", "Page"] : ["folder", "Dossier"];
    else if (ext === "pdf") label = "PDF";
    else if (["xls", "xlsx", "xlsm", "csv"].includes(ext)) label = "Tableur";
    else if (["doc", "docx"].includes(ext)) label = "Document";
    return { isWeb, name: tail || link, kind, label };
  }

  function linksHtml(links) {
    if (!links.length) return "";
    return `<ul class="evidence-links">${links
      .map((link) => {
        const d = describeLink(link);
        const action = d.isWeb
          ? `<a class="evidence-link__action" href="${escapeHtml(link)}" target="_blank" rel="noopener" aria-label="Ouvrir ${escapeHtml(d.name)} (nouvel onglet)">Ouvrir</a>`
          : `<button type="button" class="evidence-link__action js-copy-link" data-link="${escapeHtml(link)}" data-report-hide aria-label="Copier le chemin de ${escapeHtml(d.name)}" title="Le navigateur ne peut pas ouvrir un chemin réseau : copiez-le, puis collez-le dans l'explorateur">Copier le chemin</button>`;
        return `
        <li class="evidence-link evidence-link--${d.kind}">
          <span class="evidence-link__icon" title="${d.label}">${LINK_ICONS[d.kind]}</span>
          <span class="evidence-link__text"><span class="evidence-link__name">${escapeHtml(d.name)}</span><span class="evidence-link__path">${escapeHtml(link)}</span></span>
          ${action}
        </li>`;
      })
      .join("")}</ul>`;
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (err) {
      const area = document.createElement("textarea");
      area.value = text;
      area.style.cssText = "position:fixed;opacity:0;";
      document.body.appendChild(area);
      area.select();
      const ok = document.execCommand("copy");
      area.remove();
      return ok;
    }
  }

  // Une ancienne preuve « graphique » : sa description (titre, axes, requête), sans aller chercher de données.
  function graphHtml(e) {
    const cfg = e.graph_config || {};
    const axes = [cfg.x_label, cfg.y_label].filter(Boolean).join(" / ");
    return `
      <div style="margin-top:10px;padding:12px 14px;background:var(--bg);border-radius:var(--radius-sm);border:1px dashed var(--border-soft);">
        <div style="font-size:11.5px;font-weight:600;color:var(--text-faint);">Graphique (description seule)</div>
        ${cfg.title ? `<div style="font-size:12.5px;margin-top:4px;">${escapeHtml(cfg.title)}</div>` : ""}
        ${axes ? `<div style="font-size:11.5px;color:var(--text-faint);margin-top:2px;">${escapeHtml(axes)}</div>` : ""}
        ${cfg.query ? `<div class="mono" style="font-size:11px;color:var(--text-faint);margin-top:6px;">${escapeHtml(cfg.query)}</div>` : ""}
      </div>`;
  }

  function evidenceHtml(ctx, e) {
    const metricText = Object.entries(e.metrics || {})
      .map(([name, q]) => `${escapeHtml(name)} : ${escapeHtml(String(q.value))}${q.unit ? " " + escapeHtml(q.unit) : ""}`)
      .join(" · ");
    const badge = (text) => `<span class="badge badge-role" style="font-size:10.5px;margin-left:6px;">${escapeHtml(text)}</span>`;
    const { links } = e;
    const source =
      e.source && !links.includes(e.source)
        ? `<div style="font-size:12px;color:var(--text-soft);margin-top:2px;word-break:break-all;">${
            /^https?:\/\//i.test(e.source) ? `<a href="${escapeHtml(e.source)}" target="_blank" rel="noopener">${escapeHtml(e.source)}</a>` : escapeHtml(e.source)
          }</div>`
        : "";
    return `
      <div class="marked-card" style="margin-top:12px;">
        <div style="font-size:13px;font-weight:600;">${escapeHtml(e.description)}${e.step_index != null ? badge(stepLabel(ctx, e.step_index)) : ""}${EVIDENCE_KIND_LABELS[e.kind] ? badge(EVIDENCE_KIND_LABELS[e.kind]) : ""}</div>
        ${source}
        ${linksHtml(links)}
        ${metricText ? `<div class="mono" style="font-size:11.5px;color:var(--text-faint);margin-top:4px;">${metricText}</div>` : ""}
        ${e.objective ? `<div style="font-size:12px;color:var(--text-soft);margin-top:4px;">Objectif visé&nbsp;: <strong>${escapeHtml(e.objective)}</strong></div>` : ""}
        ${e.interpretation ? `<div style="font-size:12.5px;color:var(--text-soft);margin-top:6px;line-height:1.5;font-style:italic;">${escapeHtml(e.interpretation)}</div>` : ""}
        ${imagesHtml(ctx, e)}
        ${e.kind === "graph" ? graphHtml(e) : ""}
      </div>`;
  }

  function saveAnnotations(ctx, evidenceId, annotations) {
    return ctx.write(() => evidenceApi.replaceAnnotations(ctx.microprojectSlug, ctx.experimentId, ctx.versionId, evidenceId, { annotations }));
  }

  // Poser des annotations sur une image : choisir l'outil, cliquer (flèche : départ puis arrivée) ou
  // cliquer-glisser (cadre), puis enregistrer - toutes celles de l'image d'un coup.
  function wireAnnotations(ctx, list, evidenceList) {
    list.querySelectorAll(".js-remove-annotation").forEach((btn) => {
      btn.addEventListener("click", () => {
        const evidence = evidenceList.find((ev) => ev.id === btn.dataset.evidenceId);
        const index = Number(btn.dataset.index);
        if (evidence) saveAnnotations(ctx, evidence.id, evidence.annotations.filter((_, i) => i !== index));
      });
    });
    list.querySelectorAll(".js-annotation-image").forEach((container) => {
      const { evidenceId, attachmentId } = container.dataset;
      const evidence = evidenceList.find((ev) => ev.id === evidenceId);
      const toolsBar = container.closest(".evidence-image").querySelector(".js-annotation-tools");
      if (!evidence || !toolsBar) return;
      const hint = toolsBar.querySelector(".js-annotation-hint");
      const all = evidence.annotations;
      const others = all.filter((a) => a.attachment_id && a.attachment_id !== attachmentId);
      const local = all.filter((a) => !a.attachment_id || a.attachment_id === attachmentId).map((a) => ({ ...a, attachment_id: attachmentId }));
      let tool = null;
      let start = null;

      const redraw = () => {
        container.querySelector("svg")?.remove();
        container.insertAdjacentHTML("beforeend", annotationMarkersSvg(local));
      };
      const pct = (evt) => {
        const rect = container.getBoundingClientRect();
        return {
          x: Math.max(0, Math.min(100, ((evt.clientX - rect.left) / rect.width) * 100)),
          y: Math.max(0, Math.min(100, ((evt.clientY - rect.top) / rect.height) * 100)),
        };
      };
      const finish = (shape) => {
        const label = window.prompt("Libellé de l'annotation (optionnel)");
        local.push({ attachment_id: attachmentId, ...shape, label: label || null });
        redraw();
        tool = null;
        start = null;
        hint.textContent = "";
      };

      toolsBar.querySelectorAll(".js-annotation-tool").forEach((btn) => {
        btn.addEventListener("click", () => {
          tool = btn.dataset.tool;
          start = null;
          hint.textContent = tool === "arrow" ? "Cliquez le départ puis l'arrivée de la flèche." : "Cliquez-glissez pour dessiner le cadre.";
        });
      });
      container.addEventListener("mousedown", (evt) => {
        if (tool === "box") start = pct(evt);
      });
      container.addEventListener("mouseup", (evt) => {
        if (tool !== "box" || !start) return;
        const end = pct(evt);
        finish({ type: "box", x: start.x, y: start.y, x2: end.x, y2: end.y });
      });
      container.addEventListener("click", (evt) => {
        if (tool !== "arrow") return;
        const point = pct(evt);
        if (!start) {
          start = point;
          hint.textContent = "Cliquez l'arrivée de la flèche.";
        } else {
          finish({ type: "arrow", x: start.x, y: start.y, x2: point.x, y2: point.y });
        }
      });
      toolsBar.querySelector(".js-annotation-save").addEventListener("click", () => saveAnnotations(ctx, evidenceId, [...others, ...local]));
    });
  }

  // Comparer deux preuves entre elles (une mesure après un dépôt à 400 nm puis à 200 nm), sur leurs
  // mesures chiffrées - côté client, les preuves sont déjà chargées.
  function compareToolHtml(ctx, evidence) {
    if (evidence.length < 2) return "";
    const options = evidence
      .map((e) => `<option value="${escapeHtml(e.id)}">${escapeHtml(e.description)}${e.step_index != null ? " — " + escapeHtml(stepLabel(ctx, e.step_index)) : ""}</option>`)
      .join("");
    return `
      <div class="js-evidence-compare" data-report-hide style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border-soft);">
        <label style="font-size:11px;">Comparer deux preuves</label>
        <div class="field-row" style="margin-top:6px;">
          <select class="field js-compare-a" aria-label="Première preuve">${options}</select>
          <select class="field js-compare-b" aria-label="Seconde preuve">${options}</select>
        </div>
        <button class="btn btn-line btn-block js-compare-btn" type="button" style="margin-top:10px;">Comparer</button>
        <div class="js-compare-result" style="margin-top:12px;"></div>
      </div>`;
  }

  function wireCompareTool(el, evidence) {
    const tool = el.querySelector(".js-evidence-compare");
    if (!tool) return;
    const selectA = tool.querySelector(".js-compare-a");
    const selectB = tool.querySelector(".js-compare-b");
    const box = tool.querySelector(".js-compare-result");
    // par défaut, les deux plus récentes : « où j'en suis par rapport à juste avant »
    selectA.selectedIndex = evidence.length - 2;
    selectB.selectedIndex = evidence.length - 1;
    tool.querySelector(".js-compare-btn").addEventListener("click", () => {
      if (selectA.value === selectB.value) {
        box.innerHTML = `<div class="help">Choisissez deux preuves différentes.</div>`;
        return;
      }
      const a = evidence.find((e) => e.id === selectA.value);
      const b = evidence.find((e) => e.id === selectB.value);
      const names = [...new Set([...Object.keys(a.metrics || {}), ...Object.keys(b.metrics || {})])];
      if (!names.length) {
        box.innerHTML = `<div class="help">Aucune des deux preuves n'a de mesure chiffrée à comparer.</div>`;
        return;
      }
      const fmt = (q) => (q ? `${q.value}${q.unit ? " " + q.unit : ""}` : "—");
      const rows = names
        .map((name) => {
          const qa = (a.metrics || {})[name];
          const qb = (b.metrics || {})[name];
          let delta = "—";
          if (qa && qb && typeof qa.value === "number" && typeof qb.value === "number") {
            const d = qb.value - qa.value;
            delta = qa.unit === qb.unit ? `${d > 0 ? "+" : ""}${d}${qb.unit ? " " + qb.unit : ""}` : "unités différentes";
          }
          return `<tr><td>${escapeHtml(name)}</td><td class="mono">${escapeHtml(fmt(qa))}</td><td class="mono">${escapeHtml(fmt(qb))}</td><td class="mono">${escapeHtml(delta)}</td></tr>`;
        })
        .join("");
      box.innerHTML = `
        <table style="width:100%;font-size:12.5px;border-collapse:collapse;">
          <thead><tr style="color:var(--text-faint);text-align:left;"><th>Mesure</th><th>${escapeHtml(a.description)}</th><th>${escapeHtml(b.description)}</th><th>Écart</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>`;
    });
  }

  function formHtml(ctx) {
    const { objectives } = ctx.detail;
    const steps = ctx.process ? ctx.process.steps || [] : null;
    return `
      <form class="field-group js-evidence-form" data-report-hide style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border-soft);">
        <div><label for="evidence-description">Description</label><input class="field" id="evidence-description" placeholder="ex : mesure d'épaisseur au profilomètre" required></div>
        ${
          objectives.length
            ? `<div><label for="evidence-objective">Objectif visé (optionnel)</label><select class="field" id="evidence-objective">
                 <option value="">— aucun —</option>
                 ${objectives.map((o) => `<option value="${escapeHtml(o.name)}">${escapeHtml(o.name)}</option>`).join("")}
               </select></div>`
            : ""
        }
        <div><label for="evidence-interpretation">Interprétation (optionnel)</label><textarea class="field" id="evidence-interpretation" rows="2" placeholder="pourquoi ce résultat est cohérent avec le changement"></textarea></div>
        <div><label for="evidence-links">Liens <span class="help" style="display:inline;margin:0;font-weight:400;">- un dossier, une présentation PowerPoint, une page SharePoint… un par ligne</span></label>
          <textarea class="field" id="evidence-links" rows="2" placeholder="\\\\serveur\\partage\\Runs\\W42\\revue.pptx&#10;https://…sharepoint.com/…"></textarea></div>
        <div><label>Images <span class="help" style="display:inline;margin:0;font-weight:400;">- collez (Ctrl+V), glissez-déposez ou choisissez une ou plusieurs images</span></label>
          <div class="js-evidence-images"></div></div>
        <div><label for="evidence-source">Référence (optionnel)</label><input class="field" id="evidence-source" placeholder="appareil, fichier de mesure, référence…"></div>
        ${
          steps
            ? `<div><label for="evidence-step">Étape associée (optionnel)</label><select class="field" id="evidence-step">
                 <option value="">— aucune —</option>
                 ${steps.map((s, i) => `<option value="${i}">${escapeHtml(ExperimentVocabulary.stepLabel(s))}</option>`).join("")}
               </select></div>`
            : ""
        }
        <div class="field-row">
          <input class="field" id="evidence-metric-name" placeholder="mesure (optionnel)" aria-label="Nom de la mesure">
          <input class="field" id="evidence-metric-value" type="number" step="any" placeholder="valeur" aria-label="Valeur de la mesure">
        </div>
        <div class="error js-evidence-error" style="display:none;"></div>
        <button class="btn btn-line btn-block" type="submit">Ajouter la preuve</button>
      </form>`;
  }

  function wireForm(ctx, el) {
    const form = el.querySelector(".js-evidence-form");
    const errorBox = form.querySelector(".js-evidence-error");
    const field = (id) => form.querySelector(`#${id}`);
    const images = mountImageDrop(form.querySelector(".js-evidence-images"), {
      slug: ctx.microprojectSlug,
      purpose: "evidence",
      withKind: false,
      compact: true,
      onChange: () => (errorBox.style.display = "none"),
      onError: (err) => ctx.showError(err, errorBox),
      // coller une image ne vise ce formulaire que quand il est affiché (onglet ouvert, pas de modale)
      isActive: () => !document.querySelector("dialog[open]") && !el.closest("[hidden]"),
    });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      errorBox.style.display = "none";
      if (images.isUploading()) return ctx.showError(new Error("Une image est encore en cours d'envoi - un instant."), errorBox);
      const metricValue = field("evidence-metric-value").value;
      const step = field("evidence-step");
      const objective = field("evidence-objective");
      const body = {
        description: field("evidence-description").value,
        source: field("evidence-source").value.trim(),
        kind: "standard",
        objective: objective && objective.value ? objective.value : null,
        interpretation: field("evidence-interpretation").value.trim() || null,
        metric_name: field("evidence-metric-name").value.trim() || null,
        metric_value: metricValue ? parseFloat(metricValue) : null,
        step_index: step && step.value !== "" ? Number(step.value) : null,
        links: field("evidence-links").value.split(/\n+/).map((l) => l.trim()).filter(Boolean),
        images: images.get().map((img) => ({ image_id: img.image_id, caption: (img.caption || "").trim() || null })),
      };
      ctx.write(() => evidenceApi.add(ctx.microprojectSlug, ctx.experimentId, ctx.versionId, body), errorBox);
    });
  }

  ExperiencePage.registerPanel({
    key: "evidence",
    async mount(el, ctx) {
      const shown = ctx.versionId;
      const evidence = await evidenceApi.list(ctx.microprojectSlug, ctx.experimentId, shown);
      if (ctx.versionId !== shown) return; // la fiche a été rechargée entre-temps : ce rechargement-là remplit le panneau
      el.innerHTML = `
        <div class="js-evidence-list">${evidence.length ? evidence.map((e) => evidenceHtml(ctx, e)).join("") : `<div class="help">Aucune preuve enregistrée.</div>`}</div>
        ${compareToolHtml(ctx, evidence)}
        ${ctx.canEdit ? formHtml(ctx) : ""}`;
      const list = el.querySelector(".js-evidence-list");
      list.addEventListener("click", async (event) => {
        const btn = event.target.closest(".js-copy-link");
        if (!btn) return;
        const label = btn.textContent;
        btn.textContent = (await copyText(btn.dataset.link)) ? "Copié ✓" : "Copie impossible";
        setTimeout(() => (btn.textContent = label), 1600);
      });
      if (ctx.canEdit) {
        wireAnnotations(ctx, list, evidence);
        wireForm(ctx, el);
      }
      wireCompareTool(el, evidence);
    },
  });
})();
