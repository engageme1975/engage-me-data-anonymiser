from io import BytesIO
import time

import pandas as pd
import streamlit as st

from anonymization_core import (
    DEFAULT_ENTITY_TYPES,
    ENTITY_SPECIFIC_LABELS,
    ENTITY_TYPE_OPTIONS,
    anonymised_column_name,
    default_selected_columns,
    process_dataframe,
    write_output_workbook,
)
from beyond_recognizers import (
    residual_scan,
)

st.set_page_config(page_title="Engage-Me Data Anonymiser", layout="wide")
st.title("Engage-Me Data Anonymiser")
st.markdown("Self-hosted PII anonymisation. Data never leaves your machine.")
st.info(
    "For a simple run, keep Recommended mode on, upload your file, and click "
    "Start Anonymisation. Advanced options are below if you need them."
)

uploaded_file = st.file_uploader("Upload Excel (.xlsx) or CSV", type=["xlsx", "csv"])
score_threshold = st.slider("Detection score threshold", 0.1, 0.9, 0.45, 0.05)
recommended_mode = st.checkbox(
    "Recommended mode for non-technical users",
    value=True,
    help="Automatically selects likely comment columns and the UK-aligned redaction defaults.",
)
redaction_style = st.radio(
    "Redaction style",
    options=["Generic <REDACTED> (recommended)", "Entity-specific tags"],
    index=0,
    help=(
        "Generic is cleaner for reading. Entity-specific tags show what type of "
        "information was removed."
    ),
)

if uploaded_file is not None:
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Failed to read file: {e}")
        st.stop()

    st.subheader("Select what to anonymise")
    selected_columns = st.multiselect(
        "Select columns to anonymise",
        options=list(df.columns),
        default=default_selected_columns(list(df.columns)) if recommended_mode else [],
    )

    entity_selection_labels = [label for label, _ in ENTITY_TYPE_OPTIONS]
    default_entity_labels = [
        label for label, entity_type in ENTITY_TYPE_OPTIONS if entity_type in DEFAULT_ENTITY_TYPES
    ]
    selected_entity_labels = st.multiselect(
        "Select what to anonymise (UK recommended defaults pre-selected)",
        options=entity_selection_labels,
        default=default_entity_labels if recommended_mode else [],
    )

    selected_entity_types = {
        entity_type
        for label, entity_type in ENTITY_TYPE_OPTIONS
        if label in selected_entity_labels
    }

    if uploaded_file is not None and st.button("Start Anonymisation", type="primary"):
        if not selected_columns:
            st.error("Select at least one column to anonymise.")
            st.stop()

        if not selected_entity_types:
            st.error("Select at least one entity type to anonymise.")
            st.stop()

        start_time = time.time()
        progress_bar = st.progress(0)
        status_text = st.empty()

        def progress_callback(processed: int, total: int, message: str) -> None:
            progress = 1 if total == 0 else processed / total
            progress_bar.progress(progress)
            status_text.text(message)

        df, results_summary, residual_flags, stats = process_dataframe(
            df,
            selected_columns,
            selected_entity_types,
            redaction_style,
            score_threshold,
            progress_callback=progress_callback,
        )

        elapsed = round(time.time() - start_time, 1)
        st.success(f"Completed in {elapsed} seconds")
        st.write(f"**Records processed:** {stats['records_processed']}")
        st.write(f"**Columns anonymised:** {stats['columns_anonymised']}")
        st.write(f"**PII entities detected:** {stats['pii_entities_detected']}")
        st.write(f"**Rows with possible residual items:** {stats['rows_with_possible_residual_items']}")

        if residual_flags:
            st.warning(
                "Some possible residual patterns were found after anonymisation. "
                "These rows should be reviewed manually (see Detection Report)."
            )

        output = BytesIO()
        write_output_workbook(output, df, results_summary, residual_flags)

        st.download_button(
            label="Download Anonymised Excel + Reports",
            data=output.getvalue(),
            file_name="beyond_anonymised_results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
