SELECT
    mvep."date" AS "PL date",
    mvep."lotID" as "FDL",
    mvep.waferID as "Wafer name",
    mvep."X",
    mvep."Y",
    wvep."Recipe" AS "Recipe",
    SQRT(POW(mvep."X", 2) + POW(mvep."Y", 2)) AS "R",
    mvep."DOM_WAVELENGTH" AS "Dominant WL(nm)",
    mvep."PEAK_WAVELENGTH" AS "Peak WL (nm)",
    mvep."INTEGRATED_INT" AS "Integrated PL (a.u.)",
    mvep."FWHM" AS "FWHM (nm)"
FROM schema_defectivity."MeasurementValuesEtamaxPlato" mvep
Join schema_defectivity."WaferValueEtamax" wvep
    ON mvep.waferID = wvep.waferid
WHERE mvep.waferID = ANY(%(wafer_names)s)
    And (
    mvep."DOM_WAVELENGTH" > 0
    )
