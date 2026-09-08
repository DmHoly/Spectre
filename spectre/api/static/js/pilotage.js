/* Vue globale société : les compteurs agrégés et le leaderboard des grands thèmes, tous deux
   construits sur GET /api/management (voir spectre.api.management). Tendances / hero perfs :
   Phase 2. */

const errorBox = document.getElementById("error");

function bigStat(n, label) {
  return `<div><div style="font-size:24px;font-weight:700;">${n}</div><div style="font-size:11.5px;color:var(--text-faint);text-transform:uppercase;letter-spacing:.03em;">${label}</div></div>`;
}

function leaderboardRow(area, rank) {
  const s = area.stats;
  const rate = s.experiences ? Math.round((100 * s.concluded) / s.experiences) : 0;
  return `
    <tr style="border-top:1px solid var(--border-soft);">
      <td style="padding:9px 10px;color:var(--text-faint);width:32px;">${rank}</td>
      <td style="padding:9px 10px;font-weight:600;"><a href="/management/${encodeURIComponent(area.slug)}" style="color:inherit;">${escapeHtml(area.name)}</a></td>
      <td style="padding:9px 10px;text-align:right;">${s.microprojets}</td>
      <td style="padding:9px 10px;text-align:right;">${s.experiences}</td>
      <td style="padding:9px 10px;text-align:right;">${s.wafers}</td>
      <td style="padding:9px 10px;text-align:right;">${s.concluded}</td>
      <td style="padding:9px 10px;text-align:right;">${rate}%</td>
    </tr>`;
}

async function load() {
  let data;
  try {
    data = await api.get("/api/management");
  } catch (err) {
    errorBox.textContent = err.message || String(err);
    errorBox.style.display = "block";
    return;
  }
  const t = data.totals;
  document.getElementById("totals").innerHTML = [
    bigStat(t.themes, "thèmes"),
    bigStat(t.microprojets, "µprojets"),
    bigStat(t.experiences, "expériences"),
    bigStat(t.running, "en cours"),
    bigStat(t.concluded, "concluantes"),
    bigStat(t.wafers, "wafers"),
    bigStat(t.conclusion_rate + "%", "taux de conclusion"),
  ].join("");

  const ranked = [...data.areas].sort((a, b) => b.stats.experiences - a.stats.experiences);
  document.getElementById("leaderboard").innerHTML = `
    <thead><tr style="text-align:left;color:var(--text-faint);font-size:11.5px;text-transform:uppercase;letter-spacing:.03em;">
      <th style="padding:0 10px 8px;"></th><th style="padding:0 10px 8px;">Thème</th>
      <th style="padding:0 10px 8px;text-align:right;">µprojets</th>
      <th style="padding:0 10px 8px;text-align:right;">Expériences</th>
      <th style="padding:0 10px 8px;text-align:right;">Wafers</th>
      <th style="padding:0 10px 8px;text-align:right;">Concluantes</th>
      <th style="padding:0 10px 8px;text-align:right;">Taux</th>
    </tr></thead>
    <tbody>${ranked.map((a, i) => leaderboardRow(a, i + 1)).join("")}</tbody>`;
}

load();
