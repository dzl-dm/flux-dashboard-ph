import argparse
import sys
from pathlib import Path

import pandas as pd

# Preprocessing


def process_data(
    input_path_main,
    input_path_patients,
    input_path_ATC_mapping,
    Visit_cutoff_days=7,
    Baseline_tolerance_days=90,
):
    """
    This function preprocesses medical registry data and derives patient-level,
    medication-level, and visit-level datasets.

    Inputs:
        input_path_main (str):
            Path to the main event dataset. Must be in .csv-format. Must contain columns:
            ['patient_ref', 'encounter_ref', 'code', 'start', 'value'].

        input_path_patients (str):
            Path to patient-level dataset. Must be in .csv-format. Must contain:
            ['patient_id', 'birthdate', 'deceaseddate'].

        Visit_cutoff_days (int, default=7):
            Maximum allowed gap (in days) between consecutive events for them
            to be grouped into the same visit.

        Baseline_tolerance_days (int, default=90):
            Time window (± days around diagnosis_date) used to define baseline visits.

    Outputs:
        df_wide:
            Visit-level dataset. Each row represents a visit with:
            - visit_start / visit_end
            - measurement counts per LOINC code
            - flags for lab/RHC/PFT presence
            - baseline_flag
            - diagnosis_gap_months

        df_params:
            Patient-level dataset including:
            - demographics
            - diagnosis information
            - number of baseline and non-baseline visits
            - baseline measurement flags
            - RHC count and max diagnosis gap

        df_med:
            Medication-level dataset with first occurrence per patient and ATC code.
    """

    # define time format
    time_format = "%Y-%m-%d"

    # data load
    df_main = pd.read_csv(input_path_main)
    df_patients = pd.read_csv(input_path_patients)
    df_atc_mapping = pd.read_csv(input_path_ATC_mapping, sep=";")

    ##df_params (Ph group, year of diagnosis, age at diagnosis)
    df_main = df_main.rename(columns={"patient_ref": "patient_id"})

    # match every PH diagnosis
    pattern = r"^PH18:\d"
    df_params = df_main[df_main["code"].str.match(pattern)]

    # #---------------------------- test code for multiple diagnosis per patient (to be deleted) ---
    #     df_sample = df_params.sample(frac=0.1, random_state=42)
    #     df_sample["code"] = "PH18:6.6.6"
    #     df_params = pd.concat([df_params, df_sample], ignore_index=True)
    # #---------------------------------------------------------------------------------------------

    # identify patients with multiple PH diagnoses and assign "PH18:9" as code for those patients
    counts = df_params["patient_id"].value_counts()
    multi_ids = counts[counts > 1].index

    df_multi = df_params[df_params["patient_id"].isin(multi_ids)]
    df_single = df_params[~df_params["patient_id"].isin(multi_ids)]

    df_multi = df_multi.sort_values("start").drop_duplicates(
        subset=["patient_id"], keep="first"
    )
    df_multi["code"] = "PH18:9"

    df_params = pd.concat([df_multi, df_single], ignore_index=True)

    # merge df_patients information (birthdate, deceased, deceasedata)
    df_params = df_patients.merge(
        df_params, left_on="patient_id", right_on="patient_id", how="left"
    )

    df_params = df_params.astype(
        {
            "patient_id": "str",
            "encounter_ref": "str",
            "code": "str",
        }
    )

    # convert datatype to datetime
    df_params["birthdate"] = pd.to_datetime(df_params["birthdate"], format=time_format)
    df_params["start"] = pd.to_datetime(df_params["start"], format=time_format)
    df_params["deceaseddate"] = pd.to_datetime(
        df_params["deceaseddate"], format=time_format
    )

    # calculate "age at diagnosis"
    df_params["age_at_diagnosis"] = (
        df_params["start"].dt.year - df_params["birthdate"].dt.year
    )

    df_params.rename(
        columns={
            "code": "parameter_code",
            "start": "diagnosis_date",
        },
        inplace=True,
    )

    # #fill nan with "missing"
    # df_params.fillna({"parameter_code": "missing"}, inplace=True)

    df_params["diagnosis_year"] = df_params["diagnosis_date"].dt.year

    # Level 1 ph_groups
    df_params["ph_group"] = (
        df_params["parameter_code"]
        .astype(str)
        .str.extract(r"PH18:(?P<group>\d+)")["group"]
    )

    ## 2.2 df_med (ATC group)

    # match every ATC code --> medication
    pattern = r"ATC:\w{7}"
    df_med = df_main[df_main["code"].str.match(pattern)]

    df_med = df_med.astype(
        {
            "patient_id": "str",
            "encounter_ref": "str",
            "code": "str",
        }
    )

    # convert datatype to datetime
    df_med["start"] = pd.to_datetime(df_med["start"], format=time_format).dt.date

    # clean up data: only the first entry for specific medication per patient is relevant
    df_med = (
        df_med.sort_values("start")
        .drop_duplicates(subset=["patient_id", "code"], keep="first")
        .reset_index()
    )

    df_med = df_med.merge(
        df_atc_mapping[["med_name", "ATC_code"]],
        right_on="ATC_code",
        left_on="code",
        how="left",
    )

    df_med.drop(
        columns=["end", "type", "value", "unit", "ATC_code", "index"], inplace=True
    )

    ## df_wide visit_data (LOINC-Codes, visit_start, visit_end)

    # define relevant parameters for each measurement method
    # param_lab = [
    # "L:33762-6","L:2324-2","L:14933-6","L:718-7","L:14798-3",
    # "L:1988-5","L:14682-9","L:1742-6","L:1920-8","L:1975-2",
    # "L:2951-2","L:2885-2","L:1751-7","L:92891-1","L:6690-2",
    # "L:777-3","L:6768-6","L:77147-7"
    # ]

    # param_rhc = [
    #     "L:8414-5","L:94123-7","L:75994-4",
    #     "L:60985-9","L:8828-6","L:8760-1","L:8761-9"
    # ]

    # param_pft = [
    #     "L:20150-9","L:20152-5","L:19868-9",
    #     "L:19872-1","L:89085-5","L:98130-8"
    # ]

    param_lab = ["L:718-7"]
    param_pft = ["L:20150-9", "L:19866-3"]
    param_rhc = ["L:8414-5", "L:75994-4"]
    param_rhc_or = ["L:8736-1", "L:8737-9"]
    param_echo = ["L:77903-3"]

    # filter df_main for those rows which contain the relevant parameters
    df_filtered = df_main[
        df_main["code"].isin(
            param_lab + param_rhc + param_pft + param_echo + param_rhc_or
        )
    ].copy()

    # convert datatype to datetime
    df_filtered["start"] = pd.to_datetime(
        df_filtered["start"], format=time_format
    ).dt.date
    # sort the data to be chronological per patient
    df_filtered = df_filtered.sort_values(["patient_id", "start"])

    # function for visit_id generation
    def assign_visits(group):
        patient = group.name

        visit_number = 0
        visit_numbers = []
        prev_date = None

        # conditions for new visits
        for _, row in group.iterrows():
            new_visit = False
            # 1. no prior visit for this patient
            if prev_date is None or (row["start"] - prev_date).days > Visit_cutoff_days:
                new_visit = True

            if new_visit:
                visit_number += 1

            visit_numbers.append(visit_number)
            prev_date = row["start"]

        group["visit_number"] = visit_numbers
        group["patient_id"] = patient

        return group

    # apply the function on the data
    df_filtered = df_filtered.groupby("patient_id", group_keys=False).apply(
        assign_visits, include_groups=False
    )

    # generate the visit ids (this accounts for up to 999 visits within the "assign_visits" logic)
    df_filtered["visit_id"] = (
        df_filtered["patient_id"].astype(str)
        + "_"
        + df_filtered["visit_number"].astype(str).str.zfill(3)
    )
    # cleanup dataframe
    df_filtered = df_filtered.drop(columns=["visit_number"])
    # pivot the table into wide format
    df_wide = df_filtered.pivot_table(
        index=["patient_id", "visit_id"],
        columns="code",
        values="value",
        aggfunc="count",
    ).reset_index()

    df_wide.columns.name = None

    df_wide = df_wide.reindex(
        columns=df_wide.columns.union(
            param_lab + param_rhc + param_pft + param_echo + param_rhc_or
        )
    )

    # # flag the visits for each of the measurement methods
    # df_wide["visitw_lab"] = df_wide[param_lab].notna().all(axis=1).map({True: 1, False: np.nan})
    # df_wide["visitw_rhc"] = df_wide[param_rhc].notna().all(axis=1).map({True: 1, False: np.nan})
    # df_wide["visitw_pft"] = df_wide[param_pft].notna().all(axis=1).map({True: 1, False: np.nan})
    # df_wide["visitw_echo"] = df_wide[param_echo].notna().all(axis=1).map({True: 1, False: np.nan})

    # Compute earliest start per visit
    earliest_start = (
        df_filtered.groupby(["patient_id", "visit_id"])["start"]
        .min()
        .reset_index()
        .rename(columns={"start": "visit_start"})
    )
    # Compute latest start per visit
    latest_start = (
        df_filtered.groupby(["patient_id", "visit_id"])["start"]
        .max()
        .reset_index()
        .rename(columns={"start": "visit_end"})
    )

    # Merge it into the wide table
    df_wide = df_wide.merge(earliest_start, on=["patient_id", "visit_id"], how="left")
    df_wide = df_wide.merge(latest_start, on=["patient_id", "visit_id"], how="left")

    # convert time-columns to datetime
    df_params["diagnosis_date"] = pd.to_datetime(
        df_params["diagnosis_date"], format=time_format
    )
    df_wide["visit_start"] = pd.to_datetime(df_wide["visit_start"], format=time_format)
    df_wide["visit_end"] = pd.to_datetime(df_wide["visit_end"], format=time_format)

    # merge more information
    df_wide = df_wide.merge(
        df_params[["patient_id", "diagnosis_date"]], on="patient_id", how="left"
    )

    # flag for baseline visit (if the diagnosis is *Baseline_tolerance_days* days: before the "visit_start" OR within "visit_start" and "visit_end" OR after "visit_end")
    df_wide["baseline_flag"] = (
        df_wide["diagnosis_date"]
        >= df_wide["visit_start"] - pd.Timedelta(days=Baseline_tolerance_days)
    ) & (
        df_wide["diagnosis_date"]
        <= df_wide["visit_end"] + pd.Timedelta(days=Baseline_tolerance_days)
    )

    # flag the visits for each of the measurement methods
    df_wide["visitw_lab"] = df_wide[param_lab].notna().all(axis=1).astype(int)
    df_wide["visitw_rhc"] = df_wide[param_rhc].notna().all(axis=1).astype(
        int
    ) & df_wide[param_rhc_or].notna().any(axis=1).astype(int)
    df_wide["visitw_pft"] = df_wide[param_pft].notna().all(axis=1).astype(int)
    df_wide["visitw_echo"] = df_wide[param_echo].notna().all(axis=1).astype(int)

    # identify columns
    meta_cols = [
        "patient_id",
        "visit_id",
        "visit_start",
        "visit_end",
        "diagnosis_date",
        "baseline_flag",
        "visit_gap",
    ]
    binary_cols = ["visitw_lab", "visitw_rhc", "visitw_pft", "visitw_echo"]

    feature_cols = [col for col in df_wide.columns if col not in meta_cols]
    count_cols = [col for col in feature_cols if col not in binary_cols]

    # split baseline vs non-baseline
    df_base = df_wide[df_wide["baseline_flag"]].copy()
    df_non_base = df_wide[~df_wide["baseline_flag"]].copy()

    # count baseline visits per patient
    df_base_counts = (
        df_base.groupby("patient_id").size().reset_index(name="baseline_visit_count")
    )

    # count non-baseline visits per patient
    df_non_base_counts = (
        df_non_base.groupby("patient_id")
        .size()
        .reset_index(name="nonbaseline_visit_count")
    )

    # merge into maintable
    df_params = df_params.merge(
        df_base_counts.rename(columns={"patient_id": "patient_id"}),
        on="patient_id",
        how="left",
    ).merge(
        df_non_base_counts.rename(columns={"patient_id": "patient_id"}),
        on="patient_id",
        how="left",
    )

    # aggregate baseline visits per patient (each patient will have 1 baseline visit max)
    df_base_agg = (
        df_base.groupby("patient_id")
        .agg(
            visit_start=("visit_start", "min"),
            visit_end=("visit_end", "max"),
            diagnosis_date=("diagnosis_date", "first"),
            **{col: (col, "sum") for col in count_cols},
            **{col: (col, "max") for col in binary_cols},
        )
        .reset_index()
    )

    # assign new visit_id
    df_base_agg["visit_id"] = df_base_agg["patient_id"].astype(str) + "_BASELINE"

    # baseline flag stays True
    df_base_agg["baseline_flag"] = True

    # combine back
    df_wide = pd.concat([df_non_base, df_base_agg], ignore_index=True)

    # merge selected information into df_params
    mask = df_wide["visit_id"].str.contains("BASELINE", na=False)
    df_base = df_wide.loc[
        mask, ["visitw_lab", "visitw_rhc", "visitw_pft", "visitw_echo", "patient_id"]
    ]
    df_params = df_params.merge(
        df_base, right_on="patient_id", left_on="patient_id", how="left"
    ).rename(
        columns={
            "visitw_lab": "baseline_lab",
            "visitw_rhc": "baseline_rhc",
            "visitw_pft": "baseline_pft",
            "visitw_echo": "baseline_echo",
        }
    )
    # compute diagnosis gap in months
    df_wide["diagnosis_gap_months"] = (
        df_wide["visit_start"].dt.year - df_wide["diagnosis_date"].dt.year
    ) * 12 + (df_wide["visit_start"].dt.month - df_wide["diagnosis_date"].dt.month)

    # convert datetime to date
    df_params["birthdate"] = pd.to_datetime(
        df_params["birthdate"], format=time_format
    ).dt.date
    # df_params["start"] = pd.to_datetime(df_params["start"], format=time_format).dt.date
    df_params["deceaseddate"] = pd.to_datetime(
        df_params["deceaseddate"], format=time_format
    ).dt.date
    df_params["diagnosis_date"] = pd.to_datetime(
        df_params["diagnosis_date"], format=time_format
    ).dt.date
    df_wide["visit_start"] = pd.to_datetime(
        df_wide["visit_start"], format=time_format
    ).dt.date
    df_wide["visit_end"] = pd.to_datetime(
        df_wide["visit_end"], format=time_format
    ).dt.date
    df_wide["diagnosis_date"] = pd.to_datetime(
        df_wide["diagnosis_date"], format=time_format
    ).dt.date

    # identify patients with a baseline visit
    patients_with_baseline = df_wide.loc[
        df_wide["visit_id"].str.endswith("BASELINE"), "patient_id"
    ].unique()
    # compute the number of RHC per patient
    df_n_rhc = (
        df_wide[df_wide["patient_id"].isin(patients_with_baseline)]
        .groupby("patient_id")["visitw_rhc"]
        .sum()
        .reset_index(name="fcath_count")
    )

    # identify the max "diagnosis_gap" per patient
    df_max_gap = (
        df_wide.groupby("patient_id")["diagnosis_gap_months"]
        .max()
        .reset_index(name="max_diagnosis_gap_months")
    )

    df_lat_visit = (
        df_wide.groupby("patient_id")["visit_end"]
        .max()
        .reset_index(name="latest_visit_date")
    )

    # merge df_max_gap, df_lat_visit, and df_n_rhc into df_params
    df_params = df_params.merge(df_n_rhc, on="patient_id", how="left")
    df_params = df_params.merge(
        df_max_gap, left_on="patient_id", right_on="patient_id", how="left"
    )
    df_params = df_params.merge(
        df_lat_visit, left_on="patient_id", right_on="patient_id", how="left"
    )

    # sort df_wide
    df_wide = df_wide.sort_values(["patient_id", "visit_start"]).reset_index(drop=True)

    # fill nans in df_wide with 0 for the count columns
    df_wide.iloc[:, :-11] = df_wide.iloc[:, :-11].fillna(0)

    df_params.fillna(
        {
            "baseline_visit_count": 0,
            "nonbaseline_visit_count": 0,
            "baseline_lab": 0,
            "baseline_rhc": 0,
            "baseline_pft": 0,
            "baseline_echo": 0,
            "fcath_count": 0,
        },
        inplace=True,
    )

    Path("data").mkdir(parents=True, exist_ok=True)
    df_wide.to_parquet("data/wide.gzip", compression="gzip")
    df_params.to_parquet("data/params.gzip", compression="gzip")
    df_med.to_parquet("data/med.gzip", compression="gzip")

    return df_wide, df_params, df_med


def main():
    p = argparse.ArgumentParser(description="Process patient data.")
    p.add_argument(
        "--input-path-main",
        help="Path to the main input file",
        default="resources/observations.csv",
    )
    p.add_argument(
        "--input-path-patients",
        help="Path to the patients file",
        default="resources/patients.csv",
    )
    p.add_argument(
        "--input-path-atc-mapping",
        help="Path to the ATC mapping file",
        default="resources/atc_mapping.csv",
    )
    p.add_argument(
        "--visit-cutoff-days",
        type=int,
        default=7,
        help="Visit cutoff in days (default: %(default)s)",
    )
    p.add_argument(
        "--baseline-tolerance-days",
        type=int,
        default=90,
        help="Baseline tolerance in days (default: %(default)s)",
    )
    args = p.parse_args()
    not_found = False
    for p in (
        args.input_path_main,
        args.input_path_patients,
        args.input_path_atc_mapping,
    ):
        if not Path(p).is_file():
            print(f"file not found: {p}")
            not_found = True
    if not_found:
        sys.exit(1)

    process_data(
        input_path_main=args.input_path_main,
        input_path_patients=args.input_path_patients,
        input_path_ATC_mapping=args.input_path_atc_mapping,
        Visit_cutoff_days=args.visit_cutoff_days,
        Baseline_tolerance_days=args.baseline_tolerance_days,
    )


if __name__ == "__main__":
    main()
