# Spectre — Design System (MASTER)

Source de vérité UI/UX du front Spectre (`spectre/api/static/`). Généré à partir du skill
**ui-ux-pro-max** (`.claude/skills/ui-ux-pro-max`, requête « scientific lab R&D data tool
dashboard », densité 7, variance 3, mouvement 3), puis **surchargé par la charte Aledia** : la
palette bleu/ambre et les polices Fira proposées par l'outil sont remplacées par celles de la
charte. Une page peut avoir ses propres règles dans `pages/<page>.md` (elles priment sur ce
fichier).

## Contraintes

- **Vanilla uniquement** : HTML + CSS + JS sans framework ni bundler (balises `<script>`).
- Tout passe par les tokens de `css/style.css` (`:root`) - pas de hex en dur dans les pages/JS.
  Les noms historiques (`--accent`, `--text-faint`, `--done`...) sont conservés : ils sont
  référencés par des centaines de styles inline.

## Style

**Minimalism & Swiss** (outil data / labo) : grille sobre, alignement à gauche, hiérarchie
typographique nette, ombres légères, **un seul accent décoratif : l'or**.
Éviter : ornements, dégradés violets/roses, emoji comme icônes, animations appuyées.

## Couleurs (charte Aledia)

| Rôle | Token | Valeur | Usage |
|---|---|---|---|
| Navy profond | `--navy` | `#0d1b3e` | titres, bouton primaire, bandeau |
| Navy dégradé | `--navy-950` → `--navy-600` | `#060e22` → `#1a2f6a` | topbar, panneau de connexion |
| Accent interactif | `--accent` | `#1a2f6a` | bordures actives, graphes |
| Lien | `--link` | `#23408e` | liens texte (9.6:1) |
| Or | `--gold` | `#c9a84c` | filets, soulignés actifs, repères - **décoratif, jamais du texte sur blanc** |
| Or clair | `--gold-light` | `#e8c97a` | texte/souligné sur fond navy |
| Or lisible | `--gold-dark` | `#8a6d1f` | texte or sur fond clair (4.9:1) |
| Fond | `--bg` | `#f5f6fa` | |
| Texte | `--text` / `--text-soft` / `--text-faint` | `#1b2440` / `#4a5470` / `#646e8c` | tous ≥ 4.5:1 sur blanc |
| Émission InGaN | `--emit-red` `--emit-green` `--emit-blue` | `#ef5a5a` / `#3ecf7a` / `#4a8cff` | **uniquement** les schémas des technos (`js/tech-art.js`, fond navy) - jamais en UI |
| Statuts | `--draft` `--running` `--done` `--abandoned` `--danger` | + `*-tint` | badges, graphe de filiation |

## Typographie

- UI : **DM Sans** 400/500/600/700 · Données, libellés techniques, dates, versions :
  **IBM Plex Mono** 400/500/600 (Google Fonts, `<link>` asynchrone - jamais `@import`).
- Petits titres de section (`.section-title`, `.page-eyebrow`) : mono, 11px, uppercase,
  interlettrage large. **Pas d'uppercase sur un texte contenant « µ »** (devient « Μ »).
- Chiffres : `font-variant-numeric: tabular-nums` (composant `.kpi`).

## Composants clés (style.css)

- **Topbar** commune (`.topbar`, sticky 60px) : logo Aledia (`/static/img/aledia-logo.svg`) |
  SPECTRE | fil d'Ariane · nav principale identique sur toutes les pages (Thèmes, Pilotage,
  Bibliothèque, Data, Documentation), état actif `aria-current="page"` posé par `common.js` ·
  utilisateur + déconnexion (icône avec `aria-label`). Filet or dégradé sous le bandeau.
- **Boutons** : `.btn-primary` navy (survol : filet or interne), `.btn-line`, `.btn-tint`,
  `.btn-danger` ; hauteur min 36px.
- **Cartes** : `.card` (rayon 10, bordure + ombre légère) ; `a.card` gagne du relief au survol.
- **KPI** : `.kpi > .kpi__value + .kpi__label` (valeur légère + libellé mono).
- **Chargement** : `.skeleton` (réserve la place, pas de saut de mise en page).
- **Onglets** `.tab.active` : souligné or · **bascule** `.view-toggle__btn.active` : pastille navy.
- **Auth** : `.auth-shell` en deux colonnes - `.auth-hero` navy (logo, accroche, diagonale
  or/bleu de la charte) + carte formulaire ; le panneau se réduit à un bandeau sous 860px.

## Règles UX (check-list avant livraison)

- [ ] Focus clavier visible (`:focus-visible`, anneau navy ; or sur fond navy)
- [ ] Contraste texte ≥ 4.5:1 ; l'or n'est jamais porteur de texte sur blanc
- [ ] `cursor: pointer` sur tout élément cliquable ; transitions 150-200ms
- [ ] `prefers-reduced-motion` respecté (coupé globalement en fin de style.css)
- [ ] Icônes SVG (trait 1.8-2, `currentColor`, `aria-hidden` si décoratives), pas d'emoji
- [ ] Responsive testé à 375 / 768 / 1024 / 1440 - aucun scroll horizontal
- [ ] Même navigation sur toutes les pages connectées
