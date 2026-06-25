# 1. Imports

import pandas as pd
import re
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.figure_factory as ff
from preprocessing import process_data
from pathlib import Path
from datetime import datetime

# st.set_page_config(layout="wide")

st.set_page_config(
    page_title="FLUX-PH Dashboard",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        # 'Get Help': 'Placeholder',
        # 'Report a bug': "Placeholder",
        'About': "# This is a header for the About section\n\nThis dashboard was created as part of a project. It allows users to explore and filter patient data related to pulmonary hypertension (PH) diagnosis, medications, and visits. The dashboard provides insights into patient demographics, follow-up times, PH group distribution, and catherization counts. Users can apply various filters to analyze specific subsets of patients based on diagnosis parameters, medication usage, and visit characteristics."
    }
)

st.title("FLUX: Feasibility & Linkage Utility for X-referencing")

st.markdown("""
        The FLUX-PH Dashboard is a tool designed to facilitate the exploration and analysis of the pulmonary hypertension (PH) patient register.\n\n It provides an interactive interface for filtering and visualizing patient demographics, diagnosis parameters, medication usage, and visit characteristics. The dashboard also allows for the export of filtered patient and visit data for further analysis or reporting. The datatables can be found in the "Data" tab.
    """)

# 2. Preprocessing
multiple_diag_data = None
# multiple_diag_data = st.toggle("Multiple diagnosis data")

if multiple_diag_data:
    @st.cache_data
    def load_data():
        df_wide = pd.read_parquet("df_wide_test.gzip")
        df_med = pd.read_parquet("df_med_test.gzip")
        df_params = pd.read_parquet("df_params_test.gzip")
        return df_wide, df_med, df_params
else:
    @st.cache_data
    def load_data():
        df_wide = pd.read_parquet("df_wide_05_19.gzip")
        df_med = pd.read_parquet("df_med_05_19.gzip")
        df_params = pd.read_parquet("df_params_05_19.gzip")
        return df_wide, df_med, df_params

df_wide, df_diag, df_params = load_data()
# df_params = df_params[df_params["birthdate"] >= pd.to_datetime("1850-01-01")]

# 3. Filter-UI Patients

st.sidebar.header("Filters")
st.sidebar.subheader("Diagnosis filters")

# 3.1 Diagnosis year filter
min_year = int(df_params["diagnosis_year"].min())
max_year = int(df_params["diagnosis_year"].max())
year_range = st.sidebar.slider("Select diagnosis years", min_value=min_year, max_value=max_year, value=(min_year, max_year))

# 3.2 Age at diagnosis filter
min_age = int(df_params["age_at_diagnosis"].min())
max_age = int(df_params["age_at_diagnosis"].max())
age_range = st.sidebar.slider("Select age at diagnosis range", min_value=min_age, max_value=max_age, value=(min_age, max_age), help="Filter patients based on their age at diagnosis")

# 3.3 Parameter code filter
parameter_codes = df_params["parameter_code"][df_params["parameter_code"] != np.nan].unique()
selected_codes = st.sidebar.multiselect("Select parameter codes", options=parameter_codes, format_func=lambda x: "Missing" if x == "nan" else str(x))

# 3.4 PH group filter
ph_groups = df_params["ph_group"].dropna().unique()
selected_ph_groups = st.sidebar.multiselect("Select PH groups", options=ph_groups)


st.sidebar.subheader("Patient filters")

# 4.1 survival status filter
status_filter = ["Alive", "Deceased"]
selected_status = st.sidebar.multiselect("Select survival status", options=status_filter)

gender_filter = df_params["gender"].unique()
selected_gender = st.sidebar.multiselect("Select gender of patients", options = gender_filter)

# 3.6 Apply filters

filtered_df_params = df_params.copy()

if len(selected_codes) != 0:
    filtered_df_params = filtered_df_params[
        (filtered_df_params["parameter_code"].isin(selected_codes))
    ]
if year_range != (min_year, max_year):
    filtered_df_params = filtered_df_params[
        (filtered_df_params["diagnosis_year"] >= year_range[0]) &
        (filtered_df_params["diagnosis_year"] <= year_range[1])
    ]
if age_range != (min_age, max_age):
    filtered_df_params = filtered_df_params[
        (filtered_df_params["age_at_diagnosis"] >= age_range[0]) &
        (filtered_df_params["age_at_diagnosis"] <= age_range[1])
    ]

if selected_ph_groups:
    filtered_df_params = filtered_df_params[filtered_df_params["ph_group"].isin(selected_ph_groups)]

if selected_gender:
    filtered_df_params = filtered_df_params[filtered_df_params["gender"].isin(selected_gender)]


if selected_status:
    mask = pd.Series(False, index=filtered_df_params.index)

    if "Alive" in selected_status:
        mask |= filtered_df_params["deceaseddate"].isna()

    if "Deceased" in selected_status:
        mask |= filtered_df_params["deceaseddate"].notna()

    filtered_df_params = filtered_df_params[mask]

# 4. Filter UI ATC group
med_counts = df_diag.groupby("patient_id")["code"].nunique().reset_index(name="med_count")

med_options = sorted(med_counts["med_count"].unique())
selected_med_counts = st.sidebar.multiselect("Select number of unique medications per patient", options=med_options, help = "Filter patients based on the number of unique medications they have been prescribed. When selecting a number only this exact number of unique medications will be included.")

# Filter specific medication

med_opt = df_diag["med_name"].unique()
selected_meds = st.sidebar.multiselect("Select specific medications", options=med_opt)

# if len(selected_med_counts) == 0:
#     selected_med_counts = med_options

df_med_filtered = df_diag.copy()

if selected_med_counts:
    df_med_filtered = df_diag[df_diag["patient_id"].isin(
        med_counts[med_counts["med_count"].isin(selected_med_counts)]["patient_id"]
    )]

if selected_meds:
    df_med_filtered = df_med_filtered[df_med_filtered["med_name"].isin(selected_meds)]

# st.sidebar.subheader("Baseline visit filters")

baseline_options = ["Any patient","Baseline visit available", "No Baseline visit available", "Baseline is only visit"]
selected_baseline = st.sidebar.radio("Filter by baseline visit", options=baseline_options, help = """- "Any patient": No filter applied based on baseline visit availability.
- "Baseline visit available": Includes only patients who have one visit labeled as a baseline visit.
- "No Baseline visit available": Includes only patients who do not have any visits labeled as a baseline visit, but atleast one visit.
- "Baseline is only visit": Includes only patients for whom the baseline visit is the only recorded visit.
                                     """)

condition_map = {
    "Baseline with HB-test": "baseline_lab",
    "Baseline with RHC": "baseline_rhc",
    "Baseline with PFT": "baseline_pft",
    "Baseline with Echo": "baseline_echo"
}

# Build checkbox UI
st.sidebar.write("Select baseline visit characteristics")
selected_baseline_columns = [
    col_name
    for label, col_name in condition_map.items()
    if st.sidebar.checkbox(label)
]

df_wide_filtered = df_wide.copy()

if selected_baseline == "Baseline is only visit":
    patient_only_one_baseline = df_params[(df_params["baseline_visit_count"] >= 1) & (df_params["nonbaseline_visit_count"].isnull())]["patient_id"].unique()
    
    filtered_df_params = filtered_df_params[
        filtered_df_params["patient_id"].isin(patient_only_one_baseline)
    ]

elif selected_baseline == "Baseline visit available":
    patients_with_baseline = filtered_df_params.loc[
        filtered_df_params["baseline_visit_count"].notnull(),
        "patient_id"
    ].unique()
    

    filtered_df_params = filtered_df_params[
        filtered_df_params["patient_id"].isin(patients_with_baseline)
    ]


elif selected_baseline == "No Baseline visit available":
    patients_with_no_baseline = filtered_df_params.loc[
        filtered_df_params["baseline_visit_count"].isnull(),
        "patient_id"
    ].unique()
    

    filtered_df_params = filtered_df_params[
        filtered_df_params["patient_id"].isin(patients_with_no_baseline)
    ]

if selected_baseline_columns is not None and len(selected_baseline_columns) > 0:
    filtered_df_params = filtered_df_params[
        filtered_df_params[selected_baseline_columns].eq(1).all(axis=1)
    ]

st.sidebar.subheader("Visit filters")
# Visit filter


condition_map = {
    "Visit with HB-test": "visitw_lab",
    "Visit with RHC": "visitw_rhc",
    "Visit with PFT": "visitw_pft",
    "Visit with Echo": "visitw_echo"
}

# Build checkbox UI
selected_columns = [
    col_name
    for label, col_name in condition_map.items()
    if st.sidebar.checkbox(label)
]



threshold_activator = st.sidebar.toggle("Enable filter: follow-up range", help= "Filter patients bassed on the time between diagnosis and last recorded visit. Please note that activating this filter excludes patients with no diagnosis or visits.")

if threshold_activator:
    min_val = float(df_wide["diagnosis_gap_months"].min())
    max_val = float(df_wide["diagnosis_gap_months"].max())

    # initialize session state
    if "gap_range" not in st.session_state:
        st.session_state.gap_range = (min_val, max_val)

    # callback functions
    def update_from_slider():
        st.session_state.min_gap, st.session_state.max_gap = st.session_state.slider_range
        st.session_state.gap_range = st.session_state.slider_range

    def update_from_inputs():
        min_gap = st.session_state.min_gap
        max_gap = st.session_state.max_gap

        if min_gap > max_gap:
            st.warning("Invalid range: Min > Max", icon="⚠️")
            # st.stop()

        st.session_state.gap_range = (min_gap, max_gap)
        st.session_state.slider_range = (min_gap, max_gap)

    # two-sided slider
    st.sidebar.slider(
        "follow-up range (months)",
        min_value=min_val,
        max_value=max_val,
        value=st.session_state.gap_range,
        step=1.0,
        key="slider_range",
        on_change=update_from_slider
    )

    col1, col2 = st.sidebar.columns(2)

    # input boxes
    with col1:
        st.number_input(
            "Minimum months",
            min_value=min_val,
            max_value=max_val,
            value=st.session_state.gap_range[0],
            step=1.0,
            key="min_gap",
            on_change=update_from_inputs
        )

    with col2:
        st.number_input(
            "Maximum months",
            min_value=min_val,
            max_value=max_val,
            value=st.session_state.gap_range[1],
            step=1.0,
            key="max_gap",
            on_change=update_from_inputs
        )

    threshold = st.session_state.gap_range

else:
    threshold = None

if selected_columns is not None and len(selected_columns) > 0:
    df_wide_filtered = df_wide_filtered[
        df_wide_filtered[selected_columns].eq(1).all(axis=1)
    ]

if threshold is not None:
    df_wide_filtered = df_wide_filtered[
        df_wide_filtered["diagnosis_gap_months"].between(threshold[0], threshold[1])
    ]


####### crossfiltering df_wide with df_params and df_diag

if threshold or selected_columns:
    df_med_filtered = df_med_filtered[
        df_med_filtered["patient_id"].isin(df_wide_filtered["patient_id"])
    ]

    filtered_df_params = filtered_df_params[
        filtered_df_params["patient_id"].isin(df_wide_filtered["patient_id"])
    ]

# crossfiltering df_params with df_diag and df_wide

if year_range != (min_year, max_year) or age_range != (min_age, max_age) or len(selected_codes) != 0 or selected_status or selected_gender or selected_baseline == "Baseline is only visit" or selected_baseline == "Baseline visit available" or selected_baseline == "No Baseline visit available":
    df_med_filtered = df_med_filtered[
        df_med_filtered["patient_id"].isin(filtered_df_params["patient_id"])
    ]

    df_wide_filtered = df_wide_filtered[
        df_wide_filtered["patient_id"].isin(filtered_df_params["patient_id"])
    ]

# crossfiltering df_diag with df_params and df_wide

if selected_med_counts or selected_meds:
    filtered_df_params = filtered_df_params[
        filtered_df_params["patient_id"].isin(df_med_filtered["patient_id"])
    ]

    df_wide_filtered = df_wide_filtered[
        df_wide_filtered["patient_id"].isin(df_med_filtered["patient_id"])
    ]


## Filter warnings
invalid_combo = (
    selected_baseline == "Baseline is only visit"
    and threshold is not None
)
if invalid_combo:
    st.warning("""Invalid filter combination. "Baseline is only visit" and "Follow-up range" cannot be used together. ⚠️""", icon="⚠️")
    st.stop()

tab1, tab2 = st.tabs(["Dashboard", "Data"])
with tab1:
    
    # st.metric(
    #     label="Total Patients df_params",
    #     value=len(filtered_df_params)
    # )
    # st.metric(
    #     label="Total Patients df_wide",
    #     value=df_wide_filtered["patient_id"].nunique()
    # )

    col1, col2, col3 = st.columns(3)

    with col1: 
        st.metric(
        label="Patient Count",
        value=len(filtered_df_params)
        )

        st.metric(
            label="Proportion of total patients",
            value=f"{len(filtered_df_params) / len(df_params) * 100:.2f}%",
            help = "Proportion of patients in the filtered patients compared to the total patient population."
        )
    with col2:
        st.metric(
        label="Number of deceased patients",
        value=(filtered_df_params["deceaseddate"].notna().sum())
        )
    # with col3:
        st.metric(
            label="Percentage of deceased patients",
            value=f"{(filtered_df_params['deceaseddate'].notna().mean() * 100):.2f}%",
            help = "Percentage of patients in the filtered patients who are deceased."
        )
    with col3:

        sumthing = ((filtered_df_params["baseline_visit_count"] > 0)
                & (filtered_df_params["baseline_lab"] == 1)
                & (filtered_df_params["baseline_rhc"] == 1)
                & (filtered_df_params["baseline_pft"] == 1)
            ).sum()
        avg_sumthing = sumthing / len(filtered_df_params) * 100 if len(filtered_df_params) > 0 else 0
        st.metric(
            label="Patients with complete baseline dataset",
            value= sumthing,
            help = "Number of patients with a complete set of baseline data. This includes: Laboratory values, right heart catheterization, echocardiography, and pulmonary function test."
        )

       
        st.metric(
            label="Percentage of patients with complete baseline dataset",
            value=f"{avg_sumthing:.2f}%",
                help = "Percentage of patients in the filtered patients with complete baseline data."
        )

    col1, col2 = st.columns(2)
    with col1:
        
        st.subheader("Distribution of Age at Diagnosis")
        
        st.metric(
            label="Median Age at Diagnosis",
            value=f"{filtered_df_params['age_at_diagnosis'].median():.2f}"
        )

        fig_age = px.histogram(
            filtered_df_params["age_at_diagnosis"].dropna(),
            x="age_at_diagnosis",
            nbins=20,
            title="Age Distribution",
            color_discrete_sequence=px.colors.sequential.Cividis
        )
        st.plotly_chart(fig_age, width='stretch')
    
        

        # Sex distribution

        st.subheader("Sex Distribution")

        sex_counts = filtered_df_params["gender"].value_counts().reset_index()
        sex_counts.columns = ["gender", "count"]

        fig_sex = px.pie(
            sex_counts,
            names="gender",
            values="count",
            title="Sex Distribution",
            color_discrete_sequence=px.colors.sequential.Cividis
        )
        st.plotly_chart(fig_sex, width='stretch')

    with col2:    
        
        #follow up time distribution

        st.subheader("Maximum Follow-up Time per patient")

        series = filtered_df_params["max_diagnosis_gap_months"].dropna()
        median_value = series.median()

        st.metric(
            label="Median of Maximum Follow-up Time per patient (months)",
            value=f"{median_value:.2f}", help = "In this case the maximum follow-up time is the time between diagnosis and the last recorded visit in months."
        )

        # 99th percentile cutoff
        # upper_limit = series.quantile(0.99)
        upper_limit = series.quantile(1)

        fig = px.histogram(
            series,
            nbins=200,
            # range_x=[-1000, upper_limit],
            title="Maximum Follow-up time per patient (months)",
            color_discrete_sequence=px.colors.sequential.Cividis,
        )

        fig.add_vline(
            x=median_value,
            line_dash="dash",
            line_color="red",
            annotation_text=f"Median: {median_value:.2f}"
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, width='stretch')
        
        st.subheader("PH Group Distribution")

        # Extract
        filtered_df_params["ph_group"] = (
            filtered_df_params["parameter_code"]
            .astype(str)
            .str.extract(r"PH18:(\d+)")[0]
        )

        # Keep as string to avoid NaN headaches
        filtered_df_params["ph_group"] = filtered_df_params["ph_group"].fillna("Missing")

        # Count
        ph_counts = (
            filtered_df_params
            .groupby("ph_group")
            .size()
            .reset_index(name="count")
        )

        ph_counts["ph_group"] = "PH" + ph_counts["ph_group"].astype(str)

        # Ensure all groups exist
        all_groups = pd.DataFrame({
            "ph_group": ["PH0","PH1", "PH2", "PH3", "PH4", "PH5", "PH9","PHMissing"]
        })

        ph_counts = all_groups.merge(ph_counts, on="ph_group", how="left").fillna(0)
        
        
        # rename PHMissing to Missing
        ph_counts.loc[ph_counts["ph_group"] == "PHMissing", "ph_group"] = "Missing"
        ph_counts.loc[ph_counts["ph_group"] == "PH9", "ph_group"] = "Multiple"

        # Sort with Missing last
        order = ["PH0","PH1", "PH2", "PH3", "PH4", "PH5","Multiple","Missing"]
        ph_counts["ph_group"] = pd.Categorical(ph_counts["ph_group"], categories=order, ordered=True)
        ph_counts = ph_counts.sort_values("ph_group")
        # Plot
        fig_ph = px.bar(
            ph_counts,
            x="ph_group",
            y="count",
            title="PH Group Distribution",
            color="ph_group",
            color_discrete_sequence=px.colors.qualitative.Safe,
            labels={
                "ph_group_label": "PH Group",
                "count": "Number of Observations"
            },
            category_orders={"ph_group": order}
        )

        st.plotly_chart(fig_ph, width='stretch')
       
    st.subheader("Catherizations per patient")

    # st.write("The following chart displays the distribution of follow-up catherizations. This means the first RHC is always in the baseline visit.")

    patients_with_baseline = df_wide_filtered.loc[
    df_wide_filtered["visit_id"].str.endswith("BASELINE"),
    "patient_id"
    ].unique()

    cath_counts = filtered_df_params[["fcath_count", "patient_id"]].copy()

    # Aggregate counts for bar plot
    bar_data = cath_counts["fcath_count"].value_counts().sort_index().reset_index()
    bar_data.columns = ["fcath_count", "frequency"]

    median_val = cath_counts["fcath_count"].median()

    fig_cath = px.bar(
        bar_data,
        x="fcath_count",
        y="frequency",
        title="Distribution of Right Heart Catheterizations per Patient",
        labels={"fcath_count": "Right Heart Catheterizations", "frequency": "Number of Patients"},
        color_discrete_sequence=[px.colors.sequential.Cividis[1]]
    )

    fig_cath.add_vline(
        x=median_val,
        line_dash="dash",
        line_color="red",
        annotation_text=f"Median: {median_val:.2f}",
        annotation_position="top right"
    )
    st.plotly_chart(fig_cath, width='stretch')

    st.subheader("Latest Visit Date Overview")
    
    st.markdown( """ 
            Please note that the data displayed below does not account for moved patients or for information of "time of survivalstatus confirmed".
            """)

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            label="Patients with no recorded visit",
            value=(filtered_df_params["latest_visit_date"].isna().sum())
        )
    with col2:
        st.metric(
            label="Patients with a recorded visit in the last 12 months",
            value = (
            pd.to_datetime(filtered_df_params["latest_visit_date"])
            >= pd.Timestamp.today() - pd.DateOffset(months=12)
        ).sum(),
        )
    fig_latest_visit = px.histogram(
        pd.to_datetime(filtered_df_params["latest_visit_date"].dropna()),
        x="latest_visit_date",
        nbins=20,
        title="Latest visit date distribution",
        color_discrete_sequence=px.colors.sequential.Cividis
    )


    st.plotly_chart(fig_latest_visit, width='stretch')

    st.subheader("Follow-up Count Distribution")
    followup_counts = df_wide_filtered.groupby("patient_id")["visit_id"].nunique().reset_index(name="followup_count")

    fig_followup = px.histogram(
        followup_counts["followup_count"],
        x="followup_count",
        nbins=200,
        title="Follow-up Count Distribution",
        color_discrete_sequence=px.colors.sequential.Cividis
    )
    fig_followup.add_vline(
        x=followup_counts["followup_count"].median(),
        line_dash="dash",
        line_color="red",
        annotation_text=f"Median: {followup_counts['followup_count'].median():.2f}",
        annotation_position="top right"
    )
    st.plotly_chart(fig_followup, width='stretch')
    
    st.subheader("Diagnosis Year Distribution")

    fig_diag_year = px.histogram(
        filtered_df_params["diagnosis_year"].dropna(),
        x="diagnosis_year",
        nbins=200,
        title="Diagnosis Year Distribution",
        color_discrete_sequence=px.colors.sequential.Cividis
    )

    fig_diag_year.update_xaxes(
    dtick=1, 
    tickmode="linear"
    )

    st.plotly_chart(fig_diag_year, width='stretch')

with tab2:
    st.subheader("Filtered Patients Data")
    st.dataframe(filtered_df_params.drop(columns=["type", "end", "value", "unit", "encounter_ref","deceased"]))

    st.subheader("Filtered Medication Data")
    st.dataframe(df_med_filtered)

    st.subheader("Filtered Visit Data")
    st.dataframe(df_wide_filtered)

    export_patients = df_wide_filtered[["patient_id"]]
    export_visits = df_wide_filtered[["patient_id", "visit_start","visit_end"]]

    
    TRANSFER_DIR = Path("transfer")


    if st.button("Export parquet files", icon="📤"):

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        # Output paths
        patients_file = TRANSFER_DIR / f"{timestamp}_patients.parquet"
        visits_file = TRANSFER_DIR / f"{timestamp}_visits.parquet"

        # Save parquet files
        export_patients.to_parquet(patients_file, index=False)
        export_visits.to_parquet(visits_file, index=False)

        st.success(
            f"Export completed:\n"
            f"- {patients_file.name}\n"
            f"- {visits_file.name}\n"
            f"http://localhost:8080/irgendeintool?transfer={timestamp}"
        )
