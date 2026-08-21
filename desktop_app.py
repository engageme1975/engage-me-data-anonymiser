from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd

from anonymization_core import (
    AnonymisationCancelled,
    DEFAULT_ENTITY_TYPES,
    ENTITY_TYPE_OPTIONS,
    default_selected_columns,
    load_dataframe,
    process_dataframe,
    write_output_workbook,
)

APP_VERSION = "1.1.2"
LARGE_FILE_ROW_WARNING = 3000


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, secs = divmod(seconds, 60)
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


class DesktopAnonymiserApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"Engage-Me Data Anonymiser v{APP_VERSION}")
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
        self.progress_queue: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker_thread: threading.Thread | None = None
        self.run_start_time: float | None = None
        self.controls_to_disable_during_run: list[tk.Widget] = []

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
            text=f"A simple desktop app for local anonymisation without Docker. (v{APP_VERSION})",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        file_row = ttk.Frame(self.root, padding=(16, 0, 16, 8))
        file_row.grid(row=1, column=0, sticky="ew")
        file_row.columnconfigure(1, weight=1)

        ttk.Label(file_row, text="Input file").grid(row=0, column=0, sticky="w")
        ttk.Entry(file_row, textvariable=self.file_path_var).grid(row=0, column=1, sticky="ew", padx=8)
        browse_button = ttk.Button(file_row, text="Browse", command=self.browse_input_file)
        browse_button.grid(row=0, column=2, padx=(0, 8))
        load_button = ttk.Button(file_row, text="Load", command=self.load_selected_file)
        load_button.grid(row=0, column=3)

        options = ttk.Frame(self.root, padding=(16, 0, 16, 8))
        options.grid(row=2, column=0, sticky="ew")
        options.columnconfigure(1, weight=1)
        options.columnconfigure(3, weight=1)

        recommended_checkbutton = ttk.Checkbutton(
            options,
            text="Recommended mode for non-technical users",
            variable=self.recommended_mode_var,
            command=self.apply_recommended_defaults,
        )
        recommended_checkbutton.grid(row=0, column=0, sticky="w")

        ttk.Label(options, text="Detection threshold").grid(row=0, column=2, sticky="e", padx=(24, 8))
        threshold_scale = ttk.Scale(
            options, from_=0.1, to=0.9, variable=self.score_threshold_var, orient="horizontal"
        )
        threshold_scale.grid(row=0, column=3, sticky="ew")

        style_frame = ttk.Frame(self.root, padding=(16, 0, 16, 8))
        style_frame.grid(row=3, column=0, sticky="ew")
        ttk.Label(style_frame, text="Redaction style").grid(row=0, column=0, sticky="w")
        generic_radio = ttk.Radiobutton(
            style_frame,
            text="Generic <REDACTED> (recommended)",
            value="Generic <REDACTED> (recommended)",
            variable=self.redaction_style_var,
        )
        generic_radio.grid(row=0, column=1, sticky="w", padx=(12, 0))
        entity_radio = ttk.Radiobutton(
            style_frame,
            text="Entity-specific tags",
            value="Entity-specific tags",
            variable=self.redaction_style_var,
        )
        entity_radio.grid(row=0, column=2, sticky="w", padx=(12, 0))

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
        save_as_button = ttk.Button(output_row, text="Save as", command=self.choose_output_file)
        save_as_button.grid(row=0, column=2)

        progress_row = ttk.Frame(footer)
        progress_row.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        progress_row.columnconfigure(0, weight=1)
        ttk.Progressbar(progress_row, variable=self.progress_var, maximum=100).grid(row=0, column=0, sticky="ew")
        ttk.Label(progress_row, textvariable=self.status_var).grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.controls_to_disable_during_run = [
            browse_button,
            load_button,
            recommended_checkbutton,
            threshold_scale,
            generic_radio,
            entity_radio,
            save_as_button,
            self.columns_box,
            self.entities_box,
        ]

        action_row = ttk.Frame(footer)
        action_row.grid(row=2, column=0, sticky="e", pady=(12, 0))
        self.cancel_button = ttk.Button(
            action_row, text="Cancel", command=self.cancel_anonymisation, state="disabled"
        )
        self.cancel_button.grid(row=0, column=0, padx=(0, 8))
        self.run_button = ttk.Button(action_row, text="Run anonymisation", command=self.run_anonymisation)
        self.run_button.grid(row=0, column=1)

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

        row_count = len(self.dataframe)
        status_message = f"Loaded {row_count} rows and {len(self.dataframe.columns)} columns."
        if row_count > LARGE_FILE_ROW_WARNING:
            status_message += " Large file - anonymisation will run in the background and may take a while; you can cancel anytime."
        self.status_var.set(status_message)

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
        self.run_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.cancel_event.clear()
        self.run_start_time = time.time()
        for widget in self.controls_to_disable_during_run:
            widget.configure(state="disabled")

        def progress_callback(processed: int, total: int, message: str) -> None:
            self.progress_queue.put(("progress", processed, total, message))

        def cancel_check() -> bool:
            return self.cancel_event.is_set()

        def worker() -> None:
            try:
                anonymised_df, results_summary, residual_flags, stats = process_dataframe(
                    self.dataframe,
                    selected_columns,
                    sorted(selected_entity_types),
                    self.redaction_style_var.get(),
                    float(self.score_threshold_var.get()),
                    progress_callback=progress_callback,
                    cancel_check=cancel_check,
                )
                write_output_workbook(output_path, anonymised_df, results_summary, residual_flags)
                self.progress_queue.put(("done", stats, output_path))
            except AnonymisationCancelled:
                self.progress_queue.put(("cancelled",))
            except Exception as exc:  # noqa: BLE001 - surfaced to the user via the queue
                self.progress_queue.put(("error", str(exc)))

        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()
        self.root.after(100, self._poll_progress_queue)

    def cancel_anonymisation(self) -> None:
        self.cancel_event.set()
        self.cancel_button.configure(state="disabled")
        self.status_var.set("Cancelling...")

    def _poll_progress_queue(self) -> None:
        try:
            while True:
                message = self.progress_queue.get_nowait()
                kind = message[0]

                if kind == "progress":
                    _, processed, total, status_message = message
                    progress = 100 if total == 0 else (processed / total) * 100
                    self.progress_var.set(progress)
                    if self.run_start_time is not None and 0 < processed < total:
                        elapsed = time.time() - self.run_start_time
                        estimated_total = elapsed * total / processed
                        remaining = estimated_total - elapsed
                        status_message += f" ({progress:.0f}%, about {format_duration(remaining)} remaining)"
                    self.status_var.set(status_message)

                elif kind == "done":
                    _, stats, output_path = message
                    self.progress_var.set(100)
                    elapsed = time.time() - self.run_start_time if self.run_start_time is not None else 0
                    self.status_var.set(f"Anonymisation complete in {format_duration(elapsed)}.")
                    self._finish_run()
                    residual_note = (
                        f"Rows with possible residual items: {stats['rows_with_possible_residual_items']} "
                        "(see Residual Flags sheet)\n"
                        if stats["rows_with_possible_residual_items"]
                        else ""
                    )
                    messagebox.showinfo(
                        "Done",
                        (
                            f"Completed successfully in {format_duration(elapsed)}.\n\n"
                            f"Records processed: {stats['records_processed']}\n"
                            f"Columns anonymised: {stats['columns_anonymised']}\n"
                            f"PII entities detected: {stats['pii_entities_detected']}\n"
                            f"{residual_note}"
                            f"Output saved to: {output_path}"
                        ),
                    )
                    return

                elif kind == "cancelled":
                    self.status_var.set("Anonymisation cancelled.")
                    self.progress_var.set(0)
                    self._finish_run()
                    return

                elif kind == "error":
                    _, error_message = message
                    self.status_var.set("Anonymisation failed.")
                    self._finish_run()
                    messagebox.showerror("Anonymisation failed", error_message)
                    return

        except queue.Empty:
            pass

        if self.worker_thread is not None and self.worker_thread.is_alive():
            self.root.after(100, self._poll_progress_queue)
        else:
            self._finish_run()

    def _finish_run(self) -> None:
        self.run_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        for widget in self.controls_to_disable_during_run:
            widget.configure(state="normal")

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
    # Required before anything else when a frozen (PyInstaller) app on
    # Windows may spawn worker processes - anonymization_core.py's batch
    # analyzer uses multiprocessing (n_process) to parallelise NLP across
    # CPU cores. Without this, each spawned worker would re-import this
    # module and relaunch the whole GUI instead of just running its task.
    import multiprocessing

    multiprocessing.freeze_support()
    main()
