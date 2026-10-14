/* Les champs du badge d'une équipe - couleur (la palette, ou n'importe quelle couleur) et libellé
   court (4 caractères au plus ; les initiales du nom sans lui) - avec l'aperçu du badge, partagés par
   le dialogue de création (/equipes) et celui de modification (/equipes/{slug}).

   const fields = TeamFields.mount(conteneur, nameInput);   // nameInput : le champ du nom, qui nourrit l'aperçu
   fields.set({ name, color, badge });                      // remplit les champs
   fields.value();                                          // { color, badge } à envoyer à l'API */

const TeamFields = (() => {
  const PALETTE = ["#1f6feb", "#2da44e", "#d4571a", "#8250df", "#bf3989", "#0e8a9a", "#9a6700", "#cf222e"];
  const BADGE_MAX_LENGTH = 4;

  function initialsOf(name) {
    const words = (name || "").match(/[\p{L}\p{N}]+/gu) || [];
    return (words.slice(0, BADGE_MAX_LENGTH - 1).map((word) => word[0]).join("") || (name || "").slice(0, 1)).toUpperCase();
  }

  function mount(root, nameInput) {
    root.innerHTML = `
      <div class="team-fields">
        <div>
          <span class="team-fields__label" id="${root.id}-color-label">Couleur du badge</span>
          <div class="team-fields__swatches" role="radiogroup" aria-labelledby="${root.id}-color-label">
            ${PALETTE.map(
              (color) =>
                `<button type="button" class="team-swatch" role="radio" aria-checked="false" data-color="${color}" style="--team:${color}" aria-label="Couleur ${color}"></button>`
            ).join("")}
            <input type="color" class="team-fields__custom" aria-label="Autre couleur" title="Autre couleur">
          </div>
        </div>
        <div>
          <label class="team-fields__label" for="${root.id}-badge">Libellé du badge</label>
          <input class="field team-fields__badge" id="${root.id}-badge" maxlength="${BADGE_MAX_LENGTH}" autocomplete="off">
        </div>
        <div class="team-fields__preview" aria-live="polite"></div>
      </div>`;
    const custom = root.querySelector(".team-fields__custom");
    const badgeInput = root.querySelector(".team-fields__badge");
    let color = PALETTE[0];

    function render() {
      const name = nameInput.value;
      badgeInput.placeholder = initialsOf(name) || "ÉQ";
      for (const swatch of root.querySelectorAll(".team-swatch")) swatch.setAttribute("aria-checked", String(swatch.dataset.color === color));
      custom.value = color;
      root.querySelector(".team-fields__preview").innerHTML = teamBadge({
        name: name || "Nouvelle équipe",
        color,
        short: badgeInput.value.trim() || initialsOf(name) || "ÉQ",
      });
    }

    root.addEventListener("click", (event) => {
      const swatch = event.target.closest(".team-swatch");
      if (!swatch) return;
      color = swatch.dataset.color;
      render();
    });
    custom.addEventListener("input", () => {
      color = custom.value;
      render();
    });
    badgeInput.addEventListener("input", render);
    nameInput.addEventListener("input", render);

    return {
      set({ name, color: chosen, badge }) {
        nameInput.value = name || "";
        color = chosen || PALETTE[0];
        badgeInput.value = badge || "";
        render();
      },
      value() {
        return { color, badge: badgeInput.value.trim() };
      },
    };
  }

  return { mount, PALETTE };
})();
