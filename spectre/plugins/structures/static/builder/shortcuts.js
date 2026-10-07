/* Raccourcis clavier de l'atelier (liste affichée par le bouton clavier du bandeau, ou « ? »).
   Jamais actifs pendant la saisie dans un champ ; Ctrl+Z / Ctrl+Y vivent dans history.js. */

function isTypingTarget(target) {
  const tag = (target.tagName || "").toLowerCase();
  return tag === "input" || tag === "select" || tag === "textarea" || target.isContentEditable;
}

document.addEventListener("keydown", (event) => {
  if (event.defaultPrevented || document.querySelector("dialog[open]")) return;

  if (event.key === "Escape") {
    if (!shortcutsPopover.hidden) {
      toggleShortcuts(false);
      shortcutsBtn.focus();
      return;
    }
    if (closeKindMenu({ restoreFocus: true })) return;
    if (!isTypingTarget(event.target)) clearMultiSelection();
    return;
  }
  if (isTypingTarget(event.target) || event.altKey) return;
  if (state.wizardScreen === "intention") return;
  const ctrl = event.ctrlKey || event.metaKey;
  const structure = state.wizardScreen === "structure";

  if (event.key === "?" && !ctrl) {
    event.preventDefault();
    toggleShortcuts();
    return;
  }
  if (!structure) return;

  if (!ctrl && /^[1-9]$/.test(event.key)) {
    const kind = TOOL_ORDER[parseInt(event.key, 10) - 1];
    if (!kind) return;
    event.preventDefault();
    insertStepOfKind(kind);
    return;
  }

  switch (event.key) {
    case "ArrowLeft":
    case "ArrowRight": {
      event.preventDefault();
      const delta = event.key === "ArrowLeft" ? -1 : 1;
      if (ctrl) {
        moveStep(state.selectedIndex, delta);
      } else {
        if (state.previewMode === "final") state.previewMode = "step";
        selectStep(Math.max(-1, Math.min(state.steps.length - 1, state.selectedIndex + delta)));
        scrollChipIntoView(state.selectedIndex);
        focusSelectedChip();
      }
      break;
    }
    case "Home":
      event.preventDefault();
      selectStep(-1);
      focusSelectedChip();
      break;
    case "End":
      event.preventDefault();
      selectStep(state.steps.length - 1);
      scrollChipIntoView(state.selectedIndex);
      focusSelectedChip();
      break;
    case "Delete":
    case "Backspace":
      event.preventDefault();
      deleteCurrentSelection();
      break;
    case "Enter":
      if (event.target.closest && event.target.closest(".sb-chip[data-index]")) {
        event.preventDefault();
        focusInspector();
      }
      break;
    case " ": {
      // puce focalisée au clavier : Espace la sélectionne (Ctrl+Espace : sélection multiple)
      const chip = event.target.closest && event.target.closest(".sb-chip[data-index], .sb-chip--brick");
      if (!chip) break;
      event.preventDefault();
      if (chip.dataset.brick) selectBrickGroup(chip.dataset.brick);
      else selectStep(parseInt(chip.dataset.index, 10), { toggle: ctrl });
      break;
    }
    case "d":
    case "D":
      if (ctrl) {
        event.preventDefault();
        duplicateStep(state.selectedIndex);
      }
      break;
    case "f":
    case "F":
      if (!ctrl) {
        event.preventDefault();
        setPreviewMode(state.previewMode === "final" ? "step" : "final");
      }
      break;
    default:
      break;
  }
});

function focusSelectedChip() {
  const chip = document.querySelector('#steps-list [tabindex="0"]');
  if (chip) chip.focus({ preventScroll: true });
}
