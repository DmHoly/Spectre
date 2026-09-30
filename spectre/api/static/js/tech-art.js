/* Illustrations des technologies des projets corporate - des motifs SVG sobres, dessinés sur fond
   navy (couleurs via les classes .tech-art__* de style.css, donc les tokens de la charte) :

     Native (PT2)     -> un réseau de nanofils verticaux, têtes or (la LED 3D native)
     VLC (microlink)  -> deux émetteurs reliés par des impulsions lumineuses (lien optique)
     Nova (PT1)       -> une gerbe radiale de nanofils autour d'un cœur (nova)
     autre projet     -> une trame hexagonale neutre

   techArtSvg(slug, name) choisit le motif sur le slug ou le nom du projet ; purement décoratif
   (aria-hidden). Pour une nouvelle techno : ajouter une entrée à TECH_ART_RULES. */

function techArtNative() {
  const wires = [];
  const heights = [34, 46, 40, 54, 44, 58, 48, 38, 52, 42, 56, 36, 46];
  heights.forEach((h, i) => {
    const x = 14 + i * 13;
    wires.push(`<rect class="tech-art__wire" x="${x}" y="${78 - h}" width="5" height="${h}" rx="2.5"/>`);
    wires.push(`<circle class="tech-art__cap" cx="${x + 2.5}" cy="${78 - h}" r="3.4"/>`);
  });
  return `
    <rect class="tech-art__glow" x="0" y="66" width="200" height="30"/>
    <line class="tech-art__base" x1="6" y1="79" x2="194" y2="79"/>
    ${wires.join("")}`;
}

function techArtVlc() {
  const pulses = [];
  for (let i = 0; i < 6; i++) {
    const x = 52 + i * 17;
    pulses.push(`<rect class="tech-art__pulse" x="${x}" y="46" width="${9 - (i % 3) * 2}" height="4" rx="2" style="opacity:${0.35 + i * 0.11}"/>`);
  }
  return `
    <path class="tech-art__wave" d="M40 48 C 70 18, 130 78, 160 48"/>
    <path class="tech-art__wave tech-art__wave--soft" d="M40 48 C 70 78, 130 18, 160 48"/>
    ${pulses.join("")}
    <rect class="tech-art__node" x="16" y="30" width="24" height="36" rx="5"/>
    <circle class="tech-art__cap" cx="40" cy="48" r="4.5"/>
    <rect class="tech-art__node" x="160" y="30" width="24" height="36" rx="5"/>
    <circle class="tech-art__ring" cx="160" cy="48" r="6"/>`;
}

function techArtNova() {
  const rays = [];
  const n = 16;
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    const r1 = 16;
    const r2 = i % 2 ? 34 : 42;
    const [x1, y1, x2, y2] = [100 + r1 * Math.cos(a), 48 + r1 * Math.sin(a), 100 + r2 * Math.cos(a), 48 + r2 * Math.sin(a)];
    rays.push(`<line class="tech-art__ray" x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}"/>`);
    if (i % 2 === 0) rays.push(`<circle class="tech-art__cap" cx="${x2.toFixed(1)}" cy="${y2.toFixed(1)}" r="2.6"/>`);
  }
  return `
    <circle class="tech-art__halo" cx="100" cy="48" r="46"/>
    ${rays.join("")}
    <polygon class="tech-art__core" points="100,36 110.4,42 110.4,54 100,60 89.6,54 89.6,42"/>`;
}

function techArtDefault() {
  const cells = [];
  for (let row = 0; row < 4; row++) {
    for (let col = 0; col < 9; col++) {
      const cx = 24 + col * 19 + (row % 2) * 9.5;
      const cy = 20 + row * 18;
      cells.push(`<circle class="tech-art__dot" cx="${cx}" cy="${cy}" r="${(row + col) % 5 === 0 ? 3.2 : 2}"/>`);
    }
  }
  return cells.join("");
}

const TECH_ART_RULES = [
  [/native|pt2/i, techArtNative],
  [/vlc|microlink|datacom/i, techArtVlc],
  [/nova|pt1/i, techArtNova],
];

function techArtSvg(slug, name) {
  const key = `${slug || ""} ${name || ""}`;
  const rule = TECH_ART_RULES.find(([re]) => re.test(key));
  const body = (rule ? rule[1] : techArtDefault)();
  return `<svg class="tech-art" viewBox="0 0 200 96" preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false">${body}</svg>`;
}
