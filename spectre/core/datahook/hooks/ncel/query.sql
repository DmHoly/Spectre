SELECT
    n.n_fk_device AS d_pk,
    n.n_time_off AS time_off,
    n.n_time_on AS time_on,
    n.n_filter AS filter,
    t."Test_Date",
    w.wafer_name,
    d."Block_X_Coordinate" AS x_position,
    d."Block_Y_Coordinate" AS y_position,
    nca.*
FROM
    public.ncel n
JOIN
    public."Test" t ON n.n_fk_test = t."PK_Test"
JOIN
    schema_gozer.wafer w ON t.fk_wafer = w.pk_wafer
JOIN
    public."Devices" d ON n.n_fk_device = d."PK_Devices"
JOIN
    public.ncel_analysis nca ON n.n_pk_ncel = nca.na_fk_ncel
WHERE
    nca.na_jpv_max IS NOT NULL AND w.wafer_name = ANY(%(wafer_names)s);
