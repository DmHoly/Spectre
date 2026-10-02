/* Tableau : les lignes telles que la requête les renvoie, colonnes au choix, triables d'un clic
   sur l'en-tête. Accepte tout jeu de données - c'est la vue de repli. */
DataViz.register({
  key: "table",
  label: "Tableau",
  description: "Les lignes telles que renvoyées, colonnes au choix, triables.",
  accepts: (ds) => ds.columns.length > 0,
  options: () => [
    { key: "columns", label: "Colonnes", type: "columns", filter: "any" },
    { key: "limit", label: "Lignes affichées (max.)", type: "number", min: 10, max: 2000, step: 10 },
  ],
  defaults: (ds) => ({
    columns: ds.columns.filter((c) => DataViz.kind(ds, c) !== "vector").slice(0, 10),
    limit: 200,
  }),
  render(el, ds, o) {
    const columns = (o.columns && o.columns.length ? o.columns : ds.columns).filter((c) => DataViz.has(ds, c));
    const idx = columns.map((c) => DataViz.colIndex(ds, c));
    const limit = Math.max(10, Number(o.limit) || 200);
    let sortCol = -1;
    let sortDir = 1;
    const cellText = (v) => (Array.isArray(v) ? `[${v.length} pts]` : v === null || v === undefined ? "" : typeof v === "number" ? DataViz.fmt(v) : String(v));
    const paint = () => {
      const rows = ds.rows.slice();
      if (sortCol >= 0) {
        const i = idx[sortCol];
        rows.sort((a, b) => {
          const x = a[i];
          const y = b[i];
          if (x === y) return 0;
          if (x === null || x === undefined) return 1;
          if (y === null || y === undefined) return -1;
          return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y))) * sortDir;
        });
      }
      el.innerHTML = `
        <div class="viz-table-wrap">
          <table class="viz-table">
            <thead><tr>${columns
              .map((c, k) => `<th scope="col"><button type="button" data-col="${k}" aria-label="Trier par ${DataViz.esc(c)}">${DataViz.esc(c)}${k === sortCol ? (sortDir > 0 ? " ▲" : " ▼") : ""}</button></th>`)
              .join("")}</tr></thead>
            <tbody>${rows
              .slice(0, limit)
              .map((r) => `<tr>${idx.map((i) => `<td>${DataViz.esc(cellText(r[i]))}</td>`).join("")}</tr>`)
              .join("")}</tbody>
          </table>
        </div>
        <div class="viz-foot">${ds.rows.length > limit ? `${limit} lignes affichées sur ${ds.rows.length}` : `${ds.rows.length} ligne${ds.rows.length > 1 ? "s" : ""}`}</div>`;
      el.querySelectorAll("th button").forEach((btn) =>
        btn.addEventListener("click", () => {
          const k = Number(btn.dataset.col);
          sortDir = k === sortCol ? -sortDir : 1;
          sortCol = k;
          paint();
        })
      );
    };
    paint();
  },
});
