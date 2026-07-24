from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd

from anonymization_core import (
    DEFAULT_ENTITY_TYPES,
    ENTITY_TYPE_OPTIONS,
    default_selected_columns,
    load_dataframe,
    process_dataframe,
    write_output_workbook,
)


class DesktopAnonymiserApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Engage-Me Data Anonymiser")
        self.root.geometry("1020x720")
        self.root.minsize(920, 640)

        self.file_path_var = tk.StringVar()
        self.output_path_var = tk.StringVar()
        self.recommended_mode_var = tk.BooleanVar(value=True)
        self.redaction_style_var = tk.StringVar(value="Generic <REDACTED> (recommended)")
        self.score_threshold_var = tk.DoubleVar(value=0.45)
        self.status_var = tk.StringVar(value="Load a CSV or Excel file to begin.")
        self.progress_var = tk.DoubleVar(value=0.0)

        self.dataframe = None

        self._build_ui()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, padding=16)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="Engage-Me Data Anonymiser", font=("Segoe UI", 18, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        ttk.Label(
            header,
            text="A simple desktop app for local anonymisation without Docker.",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        file_row = ttk.Frame(self.root, padding=(16, 0, 16, 8))
        file_row.grid(row=1, column=0, sticky="ew")
        file_row.columnconfigure(1, weight=1)

        ttk.Label(file_row, text="Input file").grid(row=0, column=0, sticky="w")
        ttk.Entry(file_row, textvariable=self.file_path_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(file_row, text="Browse", command=self.browse_input_file).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(file_row, text="Load", command=self.load_selected_file).grid(row=0, column=3)

        options = ttk.Frame(self.root, padding=(16, 0, 16, 8))
        options.grid(row=2, column=0, sticky="ew")
        options.columnconfigure(1, weight=1)
        options.columnconfigure(3, weight=1)

        ttk.Checkbutton(
            options,
            text="Recommended mode for non-technical users",
            variable=self.recommended_mode_var,
            command=self.apply_recommended_defaults,
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(options, text="Detection threshold").grid(row=0, column=2, sticky="e", padx=(24, 8))
        ttk.Scale(options, from_=0.1, to=0.9, variable=self.score_threshold_var, orient="horizontal").grid(
            row=0, column=3, sticky="ew"
        )

        style_frame = ttk.Frame(self.root, padding=(16, 0, 16, 8))
        style_frame.grid(row=3, column=0, sticky="ew")
        ttk.Label(style_frame, text="Redaction style").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            style_frame,
            text="Generic <REDACTED> (recommended)",
            value="Generic <REDACTED> (recommended)",
            variable=self.redaction_style_var,
        ).grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Radiobutton(
            style_frame,
            text="Entity-specific tags",
            value="Entity-specific tags",
            variable=self.redaction_style_var,
        ).grid(row=0, column=2, sticky="w", padx=(12, 0))

        body = ttk.Frame(self.root, padding=16)
        body.grid(row=4, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        self.columns_box = self._make_listbox_section(body, "Columns to anonymise", 0)
        self.entities_box = self._make_listbox_section(body, "Entity types to anonymise", 1)

        footer = ttk.Frame(self.root, padding=(16, 0, 16, 16))
        footer.grid(row=5, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)

        output_row = ttk.Frame(footer)
        output_row.grid(row=0, column=0, sticky="ew")
        output_row.columnconfigure(1, weight=1)
        ttk.Label(output_row, text="Output file").grid(row=0, column=0, sticky="w")
        ttk.Entry(output_row, textvariable=self.output_path_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(output_row, text="Save as", command=self.choose_output_file).grid(row=0, column=2)

        progress_row = ttk.Frame(footer)
        progress_row.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        progress_row.columnconfigure(0, weight=1)
        ttk.Progressbar(progress_row, variable=self.progress_var, maximum=100).grid(row=0, column=0, sticky="ew")
        ttk.Label(progress_row, textvariable=self.status_var).grid(row=1, column=0, sticky="w", pady=(6, 0))

        action_row = ttk.Frame(footer)
        action_row.grid(row=2, column=0, sticky="e", pady=(12, 0))
        ttk.Button(action_row, text="Run anonymisation", command=self.run_anonymisation).grid(row=0, column=0)

    def _make_listbox_section(self, parent: ttk.Frame, title: str, column: int) -> tk.Listbox:
        container = ttk.Frame(parent, padding=(0, 0, 12 if column == 0 else 0, 0))
        container.grid(row=0, column=column, sticky="nsew")
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        ttk.Label(container, text=title).grid(row=0, column=0, sticky="w")

        list_frame = ttk.Frame(container)
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        listbox = tk.Listbox(list_frame, selectmode="extended", height=14, exportselection=False)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        return listbox

    def browse_input_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Choose CSV or Excel file",
            filetypes=[("Excel files", "*.xlsx"), ("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not file_path:
            return
        self.file_path_var.set(file_path)
        self.output_path_var.set(str(Path(file_path).with_name(f"{Path(file_path).stem}_anonymised.xlsx")))

    def load_selected_file(self) -> None:
        file_path = self.file_path_var.get().strip()
        if not file_path:
            messagebox.showerror("Missing file", "Choose a CSV or Excel file first.")
            return

        try:
            self.dataframe = load_dataframe(file_path)
        except Exception as exc:
            messagebox.showerror("Failed to load file", str(exc))
            return

        self._populate_listbox(self.columns_box, list(self.dataframe.columns))
        self._populate_listbox(self.entities_box, [label for label, _ in ENTITY_TYPE_OPTIONS])
        self.apply_recommended_defaults()

        if not self.output_path_var.get().strip():
            self.output_path_var.set(str(Path(file_path).with_name(f"{Path(file_path).stem}_anonymised.xlsx")))

        self.status_var.set(f"Loaded {len(self.dataframe)} rows and {len(self.dataframe.columns)} columns.")

    def apply_recommended_defaults(self) -> None:
        if self.dataframe is None:
            return

        columns = list(self.dataframe.columns)
        selected_columns = default_selected_columns(columns) if self.recommended_mode_var.get() else []
        self._select_listbox_items(self.columns_box, selected_columns)

        selected_entity_labels = [
            label for label, entity_type in ENTITY_TYPE_OPTIONS if entity_type in DEFAULT_ENTITY_TYPES
        ] if self.recommended_mode_var.get() else []
        self._select_listbox_items(self.entities_box, selected_entity_labels)

    def choose_output_file(self) -> None:
        file_path = filedialog.asksaveasfilename(
            title="Save anonymised workbook",
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
            initialfile=self.output_path_var.get().strip() or "beyond_anonymised_results.xlsx",
        )
        if file_path:
            self.output_path_var.set(file_path)

    def run_anonymisation(self) -> None:
        if self.dataframe is None:
            messagebox.showerror("Missing file", "Load a file before running anonymisation.")
            return

        selected_columns = self._get_selected_listbox_items(self.columns_box)
        selected_entity_labels = self._get_selected_listbox_items(self.entities_box)
        selected_entity_types = {
            entity_type
            for label, entity_type in ENTITY_TYPE_OPTIONS
            if label in selected_entity_labels
        }

        if not selected_columns:
            messagebox.showerror("Missing columns", "Select at least one column to anonymise.")
            return

        if not selected_entity_types:
            messagebox.showerror("Missing entity types", "Select at least one entity type to anonymise.")
            return

        output_path = self.output_path_var.get().strip()
        if not output_path:
            output_path = str(Path(self.file_path_var.get()).with_name("beyond_anonymised_results.xlsx"))
            self.output_path_var.set(output_path)

        self.status_var.set("Running anonymisation...")
        self.progress_var.set(0)
        self.root.update_idletasks()

        def progress_callback(processed: int, total: int, message: str) -> None:
            progress = 100 if total == 0 else (processed / total) * 100
            self.progress_var.set(progress)
            self.status_var.set(message)
            self.root.update_idletasks()

        try:
            anonymised_df, results_summary, residual_flags, stats = process_dataframe(
                self.dataframe,
                selected_columns,
                sorted(selected_entity_types),
                self.redaction_style_var.get(),
                float(self.score_threshold_var.get()),
                progress_callback=progress_callback,
            )
            write_output_workbook(output_path, anonymised_df, results_summary, residual_flags)
        except Exception as exc:
            messagebox.showerror("Anonymisation failed", str(exc))
            self.status_var.set("Anonymisation failed.")
            return

        self.progress_var.set(100)
        self.status_var.set("Anonymisation complete.")

        messagebox.showinfo(
            "Done",
            (
                f"Completed successfully.\n\n"
                f"Records processed: {stats['records_processed']}\n"
                f"Columns anonymised: {stats['columns_anonymised']}\n"
                f"PII entities detected: {stats['pii_entities_detected']}\n"
                f"Output saved to: {output_path}"
            ),
        )

    def _populate_listbox(self, listbox: tk.Listbox, items: list[str]) -> None:
        listbox.delete(0, tk.END)
        for item in items:
            listbox.insert(tk.END, item)

    def _select_listbox_items(self, listbox: tk.Listbox, items: list[str]) -> None:
        listbox.selection_clear(0, tk.END)
        list_items = listbox.get(0, tk.END)
        for index, item in enumerate(list_items):
            if item in items:
                listbox.selection_set(index)

    def _get_selected_listbox_items(self, listbox: tk.Listbox) -> list[str]:
        return [listbox.get(index) for index in listbox.curselection()]


def main() -> None:
    root = tk.Tk()
    try:
        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass
    DesktopAnonymiserApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
