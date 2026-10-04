/* Illustrations des technologies des projets corporate - des schémas SVG sobres, dessinés sur fond
   navy (couleurs via les classes .tech-art__* de areas.css, donc les tokens de la charte ; les
   couleurs d'émission InGaN --emit-* sont réservées à ces schémas) :

     Native (PT2)     -> réseau hexagonal de nanofils axiaux, un fil = un sous-pixel : chaque fil
                         porte sa couche InGaN rouge, verte ou bleue (triades RVB)
     VLC (microlink)  -> diagramme de l'œil (superposition de trames NRZ, ouverture de l'œil)
     Nova (PT1)       -> nanofil micrométrique cœur-coquille à sommet plat : cœur GaN, coquille
                         InGaN bleue, coquille externe, plus sa section hexagonale
     autre projet     -> une trame hexagonale neutre

   techArtSvg(slug, name) choisit le schéma sur le slug ou le nom du projet ; purement décoratif
   (aria-hidden). Pour une nouvelle techno : ajouter une entrée à TECH_ART_RULES. */

let techArtUid = 0;

const f1 = (n) => n.toFixed(1);

/** Points d'un hexagone régulier (pointe en haut si ``pointy``) centré en (cx, cy). */
function hexPoints(cx, cy, r, pointy) {
  const pts = [];
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 3) * i + (pointy ? Math.PI / 6 : 0);
    pts.push(`${f1(cx + r * Math.cos(a))},${f1(cy + r * Math.sin(a))}`);
  }
  return pts.join(" ");
}

/** Un nanofil vu de côté : prisme hexagonal (3 facettes visibles) coiffé d'une pyramide. */
function sideWire(x, base, w, h, extraClass, inner = "") {
  const top = base - h;
  const tip = top - w * 0.55;
  const a = x + w * 0.28;
  const b = x + w * 0.72;
  const cls = extraClass ? ` ${extraClass}` : "";
  return `
    <g class="tech-art__wire-g${cls}">
      <rect class="tech-art__facet-l" x="${f1(x)}" y="${f1(top)}" width="${f1(a - x)}" height="${f1(h)}"/>
      <rect class="tech-art__facet-m" x="${f1(a)}" y="${f1(top)}" width="${f1(b - a)}" height="${f1(h)}"/>
      <rect class="tech-art__facet-r" x="${f1(b)}" y="${f1(top)}" width="${f1(x + w - b)}" height="${f1(h)}"/>
      <polygon class="tech-art__facet-l" points="${f1(x)},${f1(top)} ${f1(a)},${f1(top)} ${f1(x + w / 2)},${f1(tip)}"/>
      <polygon class="tech-art__facet-m" points="${f1(a)},${f1(top)} ${f1(b)},${f1(top)} ${f1(x + w / 2)},${f1(tip)}"/>
      <polygon class="tech-art__facet-r" points="${f1(b)},${f1(top)} ${f1(x + w)},${f1(top)} ${f1(x + w / 2)},${f1(tip)}"/>
      ${inner}
    </g>`;
}

function techArtNative() {
  // Réseau hexagonal vu en légère perspective : trois rangées décalées d'un demi-pas (empilement
  // compact), de plus en plus grandes vers l'avant. Chaque fil est axial et forme un sous-pixel :
  // sa couche InGaN (bande près du sommet) est rouge, verte ou bleue, en alternance R/V/B - trois
  // fils voisins font un pixel, dont un est entouré à l'avant.
  const id = `ta-${++techArtUid}`;
  const pitch = 24;
  const rows = [
    { base: 58, w: 7, h: 24, offset: 4, cls: "tech-art__wire-g--far", shift: 1 },
    { base: 70, w: 9.5, h: 32, offset: 4 + pitch / 2, cls: "tech-art__wire-g--back", shift: 0 },
    { base: 86, w: 13, h: 42, offset: 4, cls: "", shift: 2 },
  ];
  const colors = ["red", "green", "blue"];
  const parts = [
    `<defs>${colors
      .map(
        (c) => `<radialGradient id="${id}-${c}"><stop offset="0" class="tech-art__glow-${c}"/><stop offset="1" class="tech-art__glow-${c} tech-art__glow-stop--end"/></radialGradient>`
      )
      .join("")}</defs>`,
    `<polygon class="tech-art__floor" points="0,${rows[0].base} 200,${rows[0].base} 200,${rows[2].base} 0,${rows[2].base}"/>`,
  ];
  rows.forEach((row, r) => {
    let i = 0;
    for (let cx = row.offset - pitch; cx <= 200 + pitch; cx += pitch, i++) {
      const color = colors[(i + row.shift) % 3];
      const x = cx - row.w / 2;
      const top = row.base - row.h;
      const bandY = top + row.h * 0.16;
      const bandH = Math.max(row.h * 0.13, 2.5);
      const glow = r === 2 ? `<circle cx="${f1(cx)}" cy="${f1(bandY + bandH / 2)}" r="${f1(row.w * 1.6)}" fill="url(#${id}-${color})"/>` : "";
      const band = `<rect class="tech-art__qw--${color}" x="${f1(x)}" y="${f1(bandY)}" width="${f1(row.w)}" height="${f1(bandH)}"/>
        <rect class="tech-art__shade" x="${f1(x)}" y="${f1(bandY)}" width="${f1(row.w * 0.28)}" height="${f1(bandH)}"/>
        <rect class="tech-art__shine" x="${f1(x + row.w * 0.72)}" y="${f1(bandY)}" width="${f1(row.w * 0.28)}" height="${f1(bandH)}"/>`;
      parts.push(glow + sideWire(x, row.base, row.w, row.h, row.cls, band));
    }
  });
  parts.push(`<line class="tech-art__base" x1="0" y1="${rows[2].base}" x2="200" y2="${rows[2].base}"/>`);
  // un pixel = trois sous-pixels voisins (R, V, B) de la rangée avant
  const px0 = rows[2].offset + 3 * pitch - rows[2].w / 2 - 4;
  parts.push(
    `<rect class="tech-art__pixel" x="${f1(px0)}" y="${f1(rows[2].base - rows[2].h - 12)}" width="${f1(2 * pitch + rows[2].w + 8)}" height="${f1(rows[2].h + 16)}" rx="4"/>`
  );
  return parts.join("");
}

function techArtVlc() {
  // Diagramme de l'œil : toutes les séquences de 4 bits NRZ superposées sur 2,5 temps-bit, avec un
  // peu de gigue temporelle et de bruit d'amplitude - l'ouverture de l'œil se lit au centre.
  const high = 20;
  const low = 76;
  const ui = 80;
  const edges = [20, 100, 180];
  const rise = 30; // largeur de la transition
  const smooth = (t) => (t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t));
  const traces = [];
  // gigue temporelle / bruit d'amplitude, déterministes (même dessin à chaque affichage)
  const jitters = [
    [-4, -2.2],
    [-2, 1.2],
    [0, 0],
    [1.5, -1],
    [3, 2],
    [4.5, 0.6],
  ];
  for (let seq = 0; seq < 16; seq++) {
    const bits = [0, 1, 2, 3].map((k) => (seq >> k) & 1);
    for (const [dt, dy] of jitters) {
      const pts = [];
      for (let x = 0; x <= 200; x += 2) {
        let level = bits[0];
        edges.forEach((e, k) => {
          level += (bits[k + 1] - bits[k]) * smooth((x - (e + dt) + rise / 2) / rise);
        });
        const y = low + (high - low) * level + dy * (level > 0.5 ? 1 : -1);
        pts.push(`${x === 0 ? "M" : "L"}${x},${f1(y)}`);
      }
      traces.push(`<path class="tech-art__trace" d="${pts.join("")}"/>`);
    }
  }
  const grid = [];
  for (let x = 20; x <= 180; x += ui / 2) grid.push(`<line class="tech-art__grid" x1="${x}" y1="10" x2="${x}" y2="86"/>`);
  for (const y of [high, (high + low) / 2, low]) grid.push(`<line class="tech-art__grid" x1="0" y1="${y}" x2="200" y2="${y}"/>`);
  return `
    ${grid.join("")}
    ${traces.join("")}
    <polygon class="tech-art__eye" points="${[
      [74, 48],
      [88, 32],
      [112, 32],
      [126, 48],
      [112, 64],
      [88, 64],
    ]
      .map((p) => p.join(","))
      .join(" ")}"/>`;
}

function techArtNova() {
  const base = 88;
  // Coupe longitudinale d'un nanofil micrométrique à sommet plat (plan c) : trois contours
  // emboîtés - coquille externe, coquille InGaN bleue, cœur GaN - qui suivent flancs et sommet.
  const shape = (x, w, top) => `${f1(x)},${base} ${f1(x)},${f1(top)} ${f1(x + w)},${f1(top)} ${f1(x + w)},${base}`;
  const x0 = 54;
  const w0 = 40;
  const top0 = 16;
  const layers = `
    <polygon class="tech-art__shell-out" points="${shape(x0, w0, top0)}"/>
    <polygon class="tech-art__shell-ingan" points="${shape(x0 + 6, w0 - 12, top0 + 6)}"/>
    <polygon class="tech-art__core-gan" points="${shape(x0 + 10, w0 - 20, top0 + 10)}"/>
    <rect class="tech-art__shade" x="${x0}" y="${top0}" width="6" height="${base - top0}"/>`;
  // Section hexagonale, reliée au fil par le plan de coupe.
  const cx = 150;
  const cy = 50;
  const section = `
    <line class="tech-art__cut" x1="${x0 - 6}" y1="66" x2="${x0 + w0 + 6}" y2="66"/>
    <line class="tech-art__cut" x1="${x0 + w0 + 6}" y1="66" x2="${cx - 30}" y2="${cy}"/>
    <polygon class="tech-art__shell-out" points="${hexPoints(cx, cy, 28, false)}"/>
    <polygon class="tech-art__shell-ingan" points="${hexPoints(cx, cy, 21, false)}"/>
    <polygon class="tech-art__core-gan" points="${hexPoints(cx, cy, 16.5, false)}"/>`;
  const scale = `
    <line class="tech-art__scale" x1="14" y1="${base - 8}" x2="38" y2="${base - 8}"/>
    <text class="tech-art__label" x="26" y="${base - 12}" text-anchor="middle">1 µm</text>`;
  return `
    <line class="tech-art__base" x1="0" y1="${base}" x2="200" y2="${base}"/>
    <ellipse class="tech-art__halo-blue" cx="${x0 + w0 / 2}" cy="${top0 + 18}" rx="40" ry="34"/>
    ${layers}
    ${section}
    ${scale}`;
}

function techArtDefault() {
  const cells = [];
  for (let row = 0; row < 4; row++) {
    for (let col = 0; col < 9; col++) {
      const cx = 24 + col * 19 + (row % 2) * 9.5;
      const cy = 20 + row * 18;
      cells.push(`<polygon class="tech-art__hex-top" points="${hexPoints(cx, cy, (row + col) % 5 === 0 ? 5 : 3.6, true)}"/>`);
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
