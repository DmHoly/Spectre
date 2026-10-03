/* « Télécharger le rapport » : un fichier HTML autonome, photographie de la fiche telle qu'elle est
   affichée. Chaque bloc est cloné puis débarrassé de ce qui n'a de sens que dans l'appli vivante
   (tout nœud data-report-hide : formulaire, bouton d'action, champ éditable, barre d'onglets...) ; le
   miroir texte .report-only qui l'accompagne parfois (voir plates.js) est révélé à sa place. Les
   trois onglets y figurent l'un après l'autre, quel que soit celui qui est ouvert ; les images
   servies par l'appli y sont embarquées, et les styles sont ceux de toutes les feuilles <link> de la
   page (noyau puis plugins, dans leur ordre). */

(() => {
  let ctx = null;

  function cleanSectionForReport(el, inlined = {}) {
    const clone = el.cloneNode(true);
    clone.removeAttribute("hidden");
    clone.querySelectorAll("[data-report-hide], .atlas-carousel__nav").forEach((node) => node.remove());
    clone.querySelectorAll("[id]").forEach((node) => node.removeAttribute("id")); // pas de doublons d'id dans le document
    clone.querySelectorAll("img").forEach((img) => {
      const src = img.getAttribute("src");
      if (src && inlined[src]) img.setAttribute("src", inlined[src]);
      img.removeAttribute("loading");
    });
    clone.querySelectorAll("a[href]").forEach((link) => {
      if (api.isApiUrl(link.getAttribute("href"))) link.removeAttribute("href");
    });
    return clone.outerHTML;
  }

  // Les images servies par l'API (structure en images, galerie, preuves) ne s'ouvriraient pas hors de
  // Spectre : le rapport les embarque en data: URL ; une image indisponible garde son lien d'origine.
  async function inlineReportImages(roots) {
    const sources = new Set();
    roots.forEach((root) =>
      root.querySelectorAll("img[src]").forEach((img) => {
        if (api.isApiUrl(img.getAttribute("src"))) sources.add(img.getAttribute("src"));
      })
    );
    const inlined = {};
    await Promise.all(
      [...sources].map(async (src) => {
        try {
          const blob = await api.get(src, { as: "blob", redirectOn401: false });
          inlined[src] = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(blob);
          });
        } catch (err) {
          // image indisponible : le rapport garde le lien d'origine
        }
      })
    );
    return inlined;
  }

  async function generateReportHtml() {
    const sheets = [...document.querySelectorAll('link[rel="stylesheet"]')].filter((link) => new URL(link.href).origin === window.location.origin);
    const css = (await Promise.all(sheets.map((link) => fetch(link.href).then((r) => (r.ok ? r.text() : ""))))).join("\n");
    const pageCss = [...document.querySelectorAll("head style")].map((el) => el.textContent).join("\n"); // infobulles de couches...
    const panelEls = ["panel-structure", "panel-donnees", "panel-conclusion"].map((id) => document.getElementById(id));
    const inlined = await inlineReportImages(panelEls);
    const panels = panelEls
      .map((el) => `<h2 class="report-section-title">${escapeHtml(el.dataset.reportTitle || "")}</h2>${cleanSectionForReport(el, inlined)}`)
      .join("\n");
    const sections = cleanSectionForReport(document.getElementById("header-card")) + panels;
    const generatedAt = new Intl.DateTimeFormat("fr-FR", { dateStyle: "long", timeStyle: "short" }).format(new Date());
    const project = [ctx.microproject.code, ctx.microproject.name].filter(Boolean).join(" · ");
    return `<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(ctx.detail.title)} — rapport d'expérience</title>
<style>${css}</style>
<style>${pageCss}</style>
<style>
  body{background:var(--bg);padding:28px 16px;}
  .report-page{max-width:1180px;margin:0 auto;}
  .report-banner{background:var(--surface);border:1px solid var(--border-soft);border-radius:var(--radius-sm);padding:10px 14px;margin-bottom:20px;font-size:12px;color:var(--text-faint);}
  .report-only{display:inline !important;}
  .fiche-panel{margin-bottom:8px;}
  .fiche-card__scroll,.fiche-history .timeline{max-height:none;overflow:visible;}
  @media print{body{padding:0;background:#fff;}.card{box-shadow:none;break-inside:avoid;}.report-section-title{break-after:avoid;}}
</style>
</head>
<body>
  <div class="report-page">
    <div class="report-banner">Rapport d'expérience — extrait de Spectre (µprojet « ${escapeHtml(project)} ») le ${generatedAt}. Document autonome : une photographie de cette fiche à cet instant, sans lien avec les données vivantes du µprojet.</div>
    ${sections}
  </div>
</body>
</html>`;
  }

  async function downloadReport() {
    try {
      const html = await generateReportHtml();
      const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
      const link = document.createElement("a");
      link.href = url;
      const version = ctx.isTip ? "" : `-${ctx.versionId}`;
      link.download = `rapport-${ctx.microproject.code || ctx.microprojectSlug}-${ctx.experimentId}${version}.html`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      ctx.showError(err);
    }
  }

  ExperiencePage.registerPanel({
    key: "report",
    mount(el, context) {
      if (!ctx) el.addEventListener("click", downloadReport);
      ctx = context;
    },
  });
})();
