SELECT
    ncel.n_fk_device AS d_pk,
    ncel.n_time_off AS "Time_off",
    ncel.n_time_on AS "Time_on",
    emission.nr_current AS pulse_points,
    wafer.wafer_name,
    devices."Block_X_Coordinate" AS x_position,
    devices."Block_Y_Coordinate" AS y_position,
    ncel.n_time AS "Time",
    emission.nr_row,
    emission.nr_record as r_emission,
    excitation.nr_record as r_excitation,
    test."TestEndDate" as "Test_Date",
FROM
    public.ncel
JOIN
    public."Test" test ON ncel.n_fk_test = test."PK_Test"
JOIN
    schema_gozer.wafer wafer ON test.fk_wafer = wafer.pk_wafer
JOIN
    public."Devices" devices ON ncel.n_fk_device = devices."PK_Devices"
JOIN
    public.ncel_records excitation ON ncel.n_pk_ncel = excitation.nr_fk_ncel AND excitation.nr_channel_name = 'Excitation'
JOIN
    public.ncel_records emission ON ncel.n_pk_ncel = emission.nr_fk_ncel AND emission.nr_channel_name = 'Emission' AND excitation.nr_row = emission.nr_row
WHERE
    wafer.wafer_name = ANY(%(wafer_names)s);