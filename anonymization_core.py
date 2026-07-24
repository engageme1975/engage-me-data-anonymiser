from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

import pandas as pd
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from beyond_recognizers import (
    create_beyond_analyzer,
    residual_scan,
    PERSON_FALSE_POSITIVE_ALLOW_LIST,
)


ENTITY_TYPE_OPTIONS = [
    ("Names (PERSON)", "PERSON"),
    ("Phone numbers", "PHONE_NUMBER"),
    ("Email addresses", "EMAIL_ADDRESS"),
    ("National Insurance numbers (UK_NINO)", "UK_NINO"),
    ("UK postcodes", "UK_POSTCODE"),
    ("Housing / repair / tenancy references (HOUSING_REF)", "HOUSING_REF"),
    ("Key-safe / access codes (ACCESS_CODE)", "ACCESS_CODE"),
    ("Broader locations (LOCATION)", "LOCATION"),
    ("Dates / times (DATE_TIME)", "DATE_TIME"),
    ("Organisations (ORGANIZATION)", "ORGANIZATION"),
]

DEFAULT_ENTITY_TYPES = {
    "PERSON",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "UK_NINO",
    "UK_POSTCODE",
    "HOUSING_REF",
    "ACCESS_CODE",
}

ENTITY_SPECIFIC_LABELS = {
    "PERSON": "<PERSON>",
    "PHONE_NUMBER": "<PHONE_NUMBER>",
    "EMAIL_ADDRESS": "<EMAIL>",
    "UK_NINO": "<NINO>",
    "UK_POSTCODE": "<POSTCODE>",
    "HOUSING_REF": "<HOUSING_REF>",
    "ACCESS_CODE": "<ACCESS_CODE>",
    "LOCATION": "<LOCATION>",
    "DATE_TIME": "<DATE_TIME>",
    "ORGANIZATION": "<ORGANIZATION>",
}


def default_selected_columns(columns: list[str]) -> list[str]:
    keywords = ["comment", "description", "note", "notes", "free", "text", "details", "message"]
    defaults = [
        column
        for column in columns
        if any(keyword in column.lower() for keyword in keywords)
    ]
    return defaults or columns[:1]


def anonymised_column_name(existing_columns: list[str], source_column: str) -> str:
    base_name = f"{source_column}_Anonymised"
    candidate = base_name
    suffix = 1
    while candidate in existing_columns:
        candidate = f"{base_name}_{suffix}"
        suffix += 1
    return candidate


def load_dataframe(file_path: str | Path) -> pd.DataFrame:
    path = Path(file_path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def build_operators(selected_entity_types: Iterable[str], redaction_style: str) -> dict[str, OperatorConfig]:
    if redaction_style.startswith("Generic"):
        return {"DEFAULT": OperatorConfig("replace", {"new_value": "<REDACTED>"})}

    operators = {
        entity_type: OperatorConfig("replace", {"new_value": ENTITY_SPECIFIC_LABELS[entity_type]})
        for entity_type in selected_entity_types
        if entity_type in ENTITY_SPECIFIC_LABELS
    }
    operators["DEFAULT"] = OperatorConfig("replace", {"new_value": "<REDACTED>"})
    return operators


def process_dataframe(
    df: pd.DataFrame,
    selected_columns: list[str],
    selected_entity_types: Iterable[str],
    redaction_style: str,
    score_threshold: float,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> tuple[pd.DataFrame, list[dict], list[dict], dict[str, int | float]]:
    output_df = df.copy()
    analyzer = create_beyond_analyzer(score_threshold=score_threshold)
    anonymizer = AnonymizerEngine()
    operators = build_operators(selected_entity_types, redaction_style)

    results_summary: list[dict] = []
    residual_flags: list[dict] = []
    total_cells = len(output_df) * len(selected_columns)
    processed_cells = 0

    if progress_callback is not None:
        progress_callback(processed_cells, total_cells, "Starting anonymisation...")

    for source_column in selected_columns:
        output_column = anonymised_column_name(list(output_df.columns), source_column)
        anonymised_texts = []

        for row_index, raw_text in enumerate(output_df[source_column].fillna("").astype(str)):
            analysis = analyzer.analyze(
                text=raw_text,
                language="en",
                allow_list=PERSON_FALSE_POSITIVE_ALLOW_LIST,
            )
            redaction_targets = [
                result for result in analysis if result.entity_type in selected_entity_types
            ]

            anonymised_result = anonymizer.anonymize(
                text=raw_text,
                analyzer_results=redaction_targets,
                operators=operators,
            )
            anonymised_text = anonymised_result.text
            anonymised_texts.append(anonymised_text)

            for result in redaction_targets:
                results_summary.append(
                    {
                        "source_column": source_column,
                        "output_column": output_column,
                        "row_index": row_index,
                        "entity_type": result.entity_type,
                        "score": round(result.score, 3),
                        "original_text": raw_text[result.start : result.end],
                        "start": result.start,
                        "end": result.end,
                    }
                )

            residuals = residual_scan(anonymised_text)
            if residuals:
                residual_flags.append(
                    {
                        "source_column": source_column,
                        "output_column": output_column,
                        "row_index": row_index,
                        "findings": residuals,
                    }
                )

            processed_cells += 1
            if progress_callback is not None:
                status_message = f"Processed {processed_cells} of {total_cells} cells..."
                progress_callback(processed_cells, total_cells, status_message)

        output_df[output_column] = anonymised_texts

    stats = {
        "records_processed": len(output_df),
        "columns_anonymised": len(selected_columns),
        "pii_entities_detected": len(results_summary),
        "rows_with_possible_residual_items": len(residual_flags),
        "processed_cells": processed_cells,
        "total_cells": total_cells,
    }
    return output_df, results_summary, residual_flags, stats


def write_output_workbook(destination, df: pd.DataFrame, results_summary: list[dict], residual_flags: list[dict]) -> None:
    with pd.ExcelWriter(destination, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Anonymised Data")
        pd.DataFrame(results_summary).to_excel(writer, index=False, sheet_name="Detection Report")
        if residual_flags:
            residual_rows = []
            for item in residual_flags:
                for finding in item["findings"]:
                    residual_rows.append(
                        {
                            "source_column": item["source_column"],
                            "output_column": item["output_column"],
                            "row_index": item["row_index"],
                            "label": finding["label"],
                            "text": finding["text"],
                        }
                    )
            pd.DataFrame(residual_rows).to_excel(writer, index=False, sheet_name="Residual Flags")
