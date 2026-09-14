WITH epi AS (
    SELECT DISTINCT ON (emv.fk_wafer)
        emv.fk_wafer,
        e."Run_Name",
        emv.design_mbe,
        emv.field_mbe,
        emv."Pocket",
        f."Request_Number"
    FROM schema_gozer."EpitaxyMeasuredValue" emv
    LEFT JOIN schema_gozer."Epitaxie" e ON e."PK_Epitaxie" = emv."FK_Epitaxy"
    LEFT JOIN schema_gozer."FDL" f ON emv.fk_fdl = f."PK_FDL"
    ORDER BY emv.fk_wafer
)
SELECT
    w.wafer_name,
    epi."Run_Name",
    epi.design_mbe,
    epi.field_mbe,
    epi."Pocket",
    d."Block_X_Coordinate" AS "X",
    d."Block_Y_Coordinate" AS "Y",
    d."Led_Name",
    d."Block_Label",
    t."Test_Date",
    epi."Request_Number",
    tl."Wavelength",
    tl."Spectra",
    tl."I",
    tl."V",
    tl."L",
    tl."L_lm",
    tl."EQE",
    tl."WPE",
    tl."CIEx",
    tl."CIEy",
    tl."Purity",
    tl."Lambda_Peak",
    tl."Lambda_Dominant",
    tl."Fwhm",
    tl."Peak_Intensity",
    t."Optical_Sensor"
FROM schema_gozer.wafer w
INNER JOIN public."Devices" d
    ON d.fk_wafer = w.pk_wafer
   AND d."Block_X_Coordinate" IS NOT NULL
   AND d."Block_Y_Coordinate" IS NOT NULL
INNER JOIN public."TestLed" tl ON tl."FK_Device" = d."PK_Devices"
INNER JOIN public."Test" t ON t."PK_Test" = tl."FK_Test"
LEFT JOIN epi ON epi.fk_wafer = w.pk_wafer
WHERE w.wafer_name = ANY(%(wafer_names)s);