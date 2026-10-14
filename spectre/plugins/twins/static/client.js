/* Client de l'API du plugin twins : les plaques dont la structure est celle d'une ligne du
   comparateur, à quelques variations près. */

const twinsApi = {
  // item : le jeton d'une ligne du comparateur (voir Comparator.waferItem, studyItem...) ;
  // maxVariations : 0 (identique), 1 ou 2 -> {base, max_variations, scanned, skipped, truncated,
  // twins: [{item, lasermark, label, study, microproject, version, url, variations, differences}]}
  find(item, maxVariations) {
    return api.get(api.withQuery("/api/wafer-twins", { item, max_variations: maxVariations }));
  },
};
