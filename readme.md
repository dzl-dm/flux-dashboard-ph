# FLUX: PH - Dashboard

This dashboard visualizes the most import KPIs of the PH register.

## Quickstart

Preliminary: Put `observations.csv` and `patients.csv` of the PH register into
the `resources` directory.

Then the quickstart assumes the default paths and exposes the dashboard on
the port 8501

### Python / uv

Install `uv` (`pip` also works but has no explicit instructions).

Steps:

1. `uv sync`
2. `uv run preprocessing.py`
3. `uv run streamlit run FLUX_ph_dashboard.py`

### Docker

Install docker

Steps:

1. `docker compose up`

Or alternatively without `compose`:

Steps:

1. `docker build -t flux-ph .`
2. `docker run -p 8501:8501  -v ./data:/app/data  -v ./resources:/app/resources flux-ph`

## Configuration Options

There are only two meaningful options,
which have to be decided at preprocessing time:

- `--visit-cutoff-days`
  The maximum allowed gap (in days) between consecutive events
  for them to be grouped into the same visit
- `--baseline-tolerance-days`  
  Time window (± days around diagnosis_date) used to define baseline visits.

Other than that only the paths can be set.
Please look into the respective scripts if you need to set other than
the default paths used by Quickstart.

The Dashboard itself assumes the created parquet files to be in the `data` directory.
This cannot be changed. The docker compose automatically mounts the correct paths

## Caching Mechanism

When a preprocessed files are created a manifest file is written as well.
This manifest contains the `mtime` values of the input files.
If the `mtime` of any input file changed, the intermediate files will be recreated.
If the input files are missing but the output exist, there will be no error.

This allows to change the input data and simply rebuilt the docker or run the
preprocessing separately, because resources and data are both mounted
