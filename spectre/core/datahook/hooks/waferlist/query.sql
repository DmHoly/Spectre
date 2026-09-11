SELECT
    wafer.wafer_name,
    "Epitaxie"."Run_Name",
    "Epitaxie".end_date,
    "Epitaxie".start_date,
    "Epitaxie"."Recipe_Type",
    "Epitaxie"."recipeversion",
    "Epitaxie".reactor,
    "Epitaxie"."Comments",
    "FDL_Epi"."Request_Number" AS Epi_Request_Number,
    "FDL_BW"."Request_Number" AS BW_Request_Number,
    "FDL_Test"."Request_Number" AS Test_Request_Number,
    "FDL_Epi"."Task_Code" AS Epi_Task_Code,
    "FDL_Epi".jira_platform

FROM
    schema_gozer.wafer
JOIN
    schema_gozer."EpitaxyMeasuredValue"
ON
    "EpitaxyMeasuredValue".fk_wafer = wafer.pk_wafer
JOIN
    schema_gozer."Epitaxie"
ON
    "Epitaxie"."PK_Epitaxie" = "EpitaxyMeasuredValue"."FK_Epitaxy"
LEFT OUTER JOIN
    schema_gozer."FDL" AS "FDL_Epi"
ON
    "EpitaxyMeasuredValue".fk_fdl = "FDL_Epi"."PK_FDL"
LEFT OUTER JOIN
    schema_gozer."BaseWafer"
ON
    "BaseWafer".fk_wafer = wafer.pk_wafer
LEFT OUTER JOIN
    schema_gozer."FDL" AS "FDL_BW"
ON
    "BaseWafer".fk_fdl = "FDL_BW"."PK_FDL"
LEFT OUTER JOIN
    public."Test"
ON
    "Test".fk_wafer = wafer.pk_wafer
LEFT OUTER JOIN
    schema_gozer."FDL" AS "FDL_Test"
ON
    "Test".fk_fdl = "FDL_Test"."PK_FDL"
