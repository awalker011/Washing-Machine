# Washing Machine

A local Python tool for cleaning, validating, and exporting FieldBOSS-style workbook data.

## What it does
- reads `.xlsx` or `.csv` input files
- normalizes messy legacy values where possible
- writes clean output CSVs
- writes error logs for rows that still need attention
- writes duplicate and fuzzy-duplicate logs

## Run the desktop app
After installing the project:

- launch `washing-machine`
- choose an input workbook
- choose or create an output folder
- click **Start Wash Cycle**

## Outputs
Each run produces:
- one cleaned CSV per configured entity
- one error CSV per entity
- `run_log.csv`
- `duplicate_log.csv`
