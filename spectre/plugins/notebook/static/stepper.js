/* Le stepper du procédé : une bulle par étape (son nom court), dans l'ordre du procédé, les bulles
   des étapes mesurées en rouge - pleines, la couleur n'étant jamais seule -, puis une bulle « étape
   retirée » par étape mesurée que le procédé n'a plus. Sert à la lecture d'une entrée du cahier
   (statique : il part tel quel dans le rapport) et à la boîte d'ajout, où l'on coche les bulles
   (`selectable` : des boutons à bascule, aria-pressed, Flèches/Début/Fin pour passer d'une bulle à
   l'autre). En largeur réduite, seul le stepper défile, horizontalement.

   mountStepper(el, {steps, measured, retired, selectable, onChange, label})
     steps     [{id, label, title?}] - les étapes du procédé (label : le nom court ; title : le
               libellé complet, en infobulle)
     measured  les ids des étapes mesurées (ou cochées)
     retired   les ids d'étapes mesurées qui ne sont plus dans le procédé (une bulle chacune, à la fin)
     onChange(ids)  `selectable` : les ids cochés, dans l'ordre du stepper
   Renvoie {get, set(ids)}. */

function mountStepper(el, { steps = [], measured = [], retired = [], selectable = false, onChange = () => {}, label = "Étapes du procédé" } = {}) {
  const known = new Set(steps.map((step) => step.id));
  const bubbles = [
    ...steps.map((step, i) => ({ id: step.id, number: String(i + 1), label: step.label, title: step.title || step.label, retired: false })),
    ...retired.filter((id) => !known.has(id)).map((id) => ({ id, number: "–", label: "étape retirée", title: "Étape retirée du procédé de cette version", retired: true })),
  ];
  let chosen = new Set(measured);

  function bubbleHtml(bubble) {
    const on = chosen.has(bubble.id);
    const state = bubble.retired ? " (retirée du procédé)" : "";
    const inner = `<span class="stepper__dot" aria-hidden="true">${escapeHtml(bubble.number)}</span><span class="stepper__label">${escapeHtml(bubble.label)}</span>`;
    const classes = `stepper__item${on ? " is-measured" : ""}${bubble.retired ? " is-retired" : ""}`;
    if (selectable) {
      return `<li class="${classes}"><button type="button" class="stepper__bubble" data-step="${escapeHtml(bubble.id)}" aria-pressed="${on}" title="${escapeHtml(bubble.title)}" aria-label="${escapeHtml(bubble.retired ? bubble.title : `Étape ${bubble.number} : ${bubble.label}`)}">${inner}</button></li>`;
    }
    return `<li class="${classes}"><span class="stepper__bubble" title="${escapeHtml(bubble.title)}">${inner}<span class="stepper__sr">${on ? " - mesurée" : ""}${state}</span></span></li>`;
  }

  function render() {
    const focused = selectable && el.contains(document.activeElement) ? document.activeElement.dataset.step : null;
    el.innerHTML = `<div class="stepper${selectable ? " stepper--selectable" : ""}" role="group" aria-label="${escapeHtml(label)}"><ol class="stepper__track">${bubbles.map(bubbleHtml).join("")}</ol></div>`;
    if (focused) el.querySelector(`[data-step="${CSS.escape(focused)}"]`)?.focus();
  }

  const ordered = () => bubbles.filter((bubble) => chosen.has(bubble.id)).map((bubble) => bubble.id);

  if (selectable) {
    el.addEventListener("click", (event) => {
      const bubble = event.target.closest("[data-step]");
      if (!bubble || !el.contains(bubble)) return;
      const id = bubble.dataset.step;
      if (chosen.has(id)) chosen.delete(id);
      else chosen.add(id);
      render();
      onChange(ordered());
    });
    el.addEventListener("keydown", (event) => {
      const buttons = [...el.querySelectorAll(".stepper__bubble")];
      const index = buttons.indexOf(document.activeElement);
      if (index < 0) return;
      const next = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: buttons.length - 1 }[event.key];
      if (next === undefined || !buttons[next]) return;
      event.preventDefault();
      buttons[next].focus();
      buttons[next].scrollIntoView({ block: "nearest", inline: "nearest" });
    });
  }

  render();
  return {
    get: ordered,
    set(ids) {
      chosen = new Set(ids);
      render();
    },
  };
}
