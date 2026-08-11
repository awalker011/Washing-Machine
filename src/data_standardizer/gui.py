from __future__ import annotations

import json
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from .pipeline import process_all


def get_application_root() -> Path:
    if getattr(sys, "frozen", False):
        bundled_root = getattr(sys, "_MEIPASS", None)
        if bundled_root:
            return Path(bundled_root)
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[2]


def get_default_schema_dir() -> Path:
    return get_application_root() / "schemas" / "fieldboss"


def get_default_mapping_dir() -> Path:
    return get_application_root() / "mappings" / "fieldboss"


def build_output_paths(input_path: str | Path, output_dir: str | Path | None) -> tuple[Path, Path]:
    input_file = Path(input_path).expanduser().resolve()
    if output_dir and str(output_dir).strip():
        output_root = Path(output_dir).expanduser().resolve()
    else:
        output_root = input_file.parent / f"{input_file.stem}_washed_output"

    return output_root, output_root / "logs"


def validate_run_inputs(input_path: str, output_dir: str) -> tuple[Path, Path, Path, Path]:
    if not str(input_path).strip():
        raise ValueError("Please choose an input CSV or XLSX file.")

    input_file = Path(input_path).expanduser().resolve()
    if not input_file.exists() or not input_file.is_file():
        raise FileNotFoundError(f"Input file was not found: {input_file}")

    if input_file.suffix.lower() not in {".csv", ".xlsx"}:
        raise ValueError("Only .csv and .xlsx files are supported.")

    schema_dir = get_default_schema_dir()
    mapping_dir = get_default_mapping_dir()
    if not schema_dir.exists():
        raise FileNotFoundError(f"Schema directory was not found: {schema_dir}")
    if not mapping_dir.exists():
        raise FileNotFoundError(f"Mapping directory was not found: {mapping_dir}")

    output_root, logs_root = build_output_paths(input_file, output_dir)
    return input_file, output_root, logs_root, schema_dir, mapping_dir


def format_run_summary(result: dict[str, Any]) -> str:
    lines = ["🫧 Spin cycle complete!", ""]
    totals = result.get("totals", {})
    lines.append(f"Rows read: {totals.get('rows_read', 0)}")
    lines.append(f"Rows accepted: {totals.get('rows_accepted', 0)}")
    lines.append(f"Rows rejected: {totals.get('rows_rejected', 0)}")
    lines.append("")

    for entity in result.get("entities", []):
        lines.append(
            f"• {entity.get('entity')}: "
            f"accepted {entity.get('rows_accepted', 0)}, "
            f"rejected {entity.get('rows_rejected', 0)}, "
            f"duplicates flagged {entity.get('duplicate_rows_flagged', 0)}"
        )

    duplicate_log = result.get("duplicate_log_file")
    if duplicate_log:
        lines.extend(["", f"Duplicate log: {duplicate_log}"])

    customer_summary = result.get("customer_summary_file")
    if customer_summary:
        lines.append(f"Customer summary: {customer_summary}")

    corrections_file = result.get("corrections_file")
    if corrections_file:
        lines.append(f"Rows needing correction (send back for re-run): {corrections_file}")

    return "\n".join(lines)


class WashingMachineApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Washing Machine")
        self.root.geometry("780x620")
        self.root.minsize(700, 560)
        self.root.configure(bg="#dff6ff")

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Load a workbook and start the wash cycle.")
        self.progress_text_var = tk.StringVar(value="Progress: idle")
        self.last_output_dir: Path | None = None

        self._configure_styles()
        self._build_layout()

    def _configure_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("App.TFrame", background="#dff6ff")
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("Title.TLabel", background="#dff6ff", foreground="#0b4f6c", font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background="#dff6ff", foreground="#356d82", font=("Segoe UI", 10))
        style.configure("Field.TLabel", background="#ffffff", foreground="#0b4f6c", font=("Segoe UI", 10, "bold"))
        style.configure("Status.TLabel", background="#dff6ff", foreground="#0b4f6c", font=("Segoe UI", 10, "bold"))
        style.configure("Wash.TButton", font=("Segoe UI", 10, "bold"))

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=18)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="🫧 Washing Machine 🫧", style="Title.TLabel").pack(anchor="center")
        ttk.Label(
            outer,
            text="Drop in a workbook, spin up a clean export, and catch the dirty rows in the lint trap.",
            style="Subtitle.TLabel",
        ).pack(anchor="center", pady=(0, 14))

        card = ttk.Frame(outer, style="Card.TFrame", padding=16)
        card.pack(fill="x", pady=(0, 12))

        ttk.Label(card, text="Input workbook", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        input_entry = ttk.Entry(card, textvariable=self.input_var, width=72)
        input_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(4, 12))
        ttk.Button(card, text="Browse…", command=self.browse_input).grid(row=1, column=1, sticky="ew")

        ttk.Label(card, text="Output folder", style="Field.TLabel").grid(row=2, column=0, sticky="w")
        output_entry = ttk.Entry(card, textvariable=self.output_var, width=72)
        output_entry.grid(row=3, column=0, sticky="ew", padx=(0, 8), pady=(4, 8))

        output_buttons = ttk.Frame(card, style="Card.TFrame")
        output_buttons.grid(row=3, column=1, sticky="nsew")
        ttk.Button(output_buttons, text="Choose…", command=self.browse_output).pack(fill="x")
        ttk.Button(output_buttons, text="Create…", command=self.create_output_folder).pack(fill="x", pady=(6, 0))

        hint = ttk.Label(
            card,
            text="Tip: choose an existing folder or create a new one. If left blank, a default washed-output folder is created next to the file.",
            style="Subtitle.TLabel",
            wraplength=680,
            justify="left",
        )
        hint.grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 6))

        card.columnconfigure(0, weight=1)

        button_row = ttk.Frame(outer, style="App.TFrame")
        button_row.pack(fill="x", pady=(0, 8))

        self.run_button = ttk.Button(button_row, text="▶ Start Wash Cycle", style="Wash.TButton", command=self.start_run)
        self.run_button.pack(side="left")

        self.open_button = ttk.Button(button_row, text="📂 Open Output Folder", command=self.open_output_folder)
        self.open_button.pack(side="left", padx=(8, 0))

        progress_row = ttk.Frame(outer, style="App.TFrame")
        progress_row.pack(fill="x", pady=(2, 8))
        self.progress_bar = ttk.Progressbar(progress_row, mode="determinate", maximum=100)
        self.progress_bar.pack(side="left", fill="x", expand=True)
        ttk.Label(progress_row, textvariable=self.progress_text_var, style="Subtitle.TLabel").pack(side="left", padx=(8, 0))

        ttk.Label(outer, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w", pady=(0, 8))

        self.output_text = ScrolledText(
            outer,
            height=20,
            wrap="word",
            font=("Consolas", 10),
            bg="#ffffff",
            fg="#12343b",
            insertbackground="#12343b",
        )
        self.output_text.pack(fill="both", expand=True)
        self.output_text.insert("1.0", "Ready for the next load.\n")
        self.output_text.configure(state="disabled")

    def append_output(self, text: str) -> None:
        self.output_text.configure(state="normal")
        self.output_text.insert("end", text + "\n")
        self.output_text.see("end")
        self.output_text.configure(state="disabled")

    def browse_input(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Choose a workbook or CSV",
            filetypes=[("Data files", "*.xlsx *.csv"), ("Excel workbooks", "*.xlsx"), ("CSV files", "*.csv")],
        )
        if not file_path:
            return

        self.input_var.set(file_path)
        if not self.output_var.get().strip():
            output_root, _ = build_output_paths(file_path, None)
            self.output_var.set(str(output_root))

    def browse_output(self) -> None:
        initial_dir = None
        if self.output_var.get().strip():
            initial_dir = self.output_var.get().strip()
        elif self.input_var.get().strip():
            initial_dir = str(Path(self.input_var.get().strip()).expanduser().resolve().parent)

        folder = filedialog.askdirectory(title="Choose output folder", initialdir=initial_dir)
        if folder:
            self.output_var.set(folder)

    def create_output_folder(self) -> None:
        base_dir = filedialog.askdirectory(title="Choose parent folder for the new output folder")
        if not base_dir:
            return

        folder_name = simpledialog.askstring("Create Output Folder", "New folder name:", initialvalue="washed_output")
        if not folder_name:
            return

        new_folder = Path(base_dir) / folder_name.strip()
        new_folder.mkdir(parents=True, exist_ok=True)
        self.output_var.set(str(new_folder))
        self.status_var.set(f"Created output folder: {new_folder}")

    def start_run(self) -> None:
        try:
            input_file, output_root, logs_root, schema_dir, mapping_dir = validate_run_inputs(
                self.input_var.get(),
                self.output_var.get(),
            )
        except Exception as exc:
            messagebox.showerror("Washing Machine", str(exc))
            return

        self.run_button.configure(state="disabled")
        self.status_var.set("Wash cycle running…")
        self.progress_bar.configure(maximum=100, value=0)
        self.progress_text_var.set("Progress: 0%")
        self.append_output(f"Starting wash cycle for: {input_file.name}")

        worker = threading.Thread(
            target=self._run_pipeline,
            args=(input_file, output_root, logs_root, schema_dir, mapping_dir),
            daemon=True,
        )
        worker.start()

    def _run_pipeline(
        self,
        input_file: Path,
        output_root: Path,
        logs_root: Path,
        schema_dir: Path,
        mapping_dir: Path,
    ) -> None:
        def publish_progress(event: dict[str, Any]) -> None:
            self.root.after(0, lambda payload=event: self._handle_progress_event(payload))

        try:
            output_root.mkdir(parents=True, exist_ok=True)
            logs_root.mkdir(parents=True, exist_ok=True)
            result = process_all(
                input_path=str(input_file),
                schema_path=str(schema_dir),
                mapping_path=str(mapping_dir),
                output_dir=str(output_root),
                logs_dir=str(logs_root),
                progress_callback=publish_progress,
            )
        except Exception as exc:
            detail = "\n".join(traceback.format_exception_only(type(exc), exc)).strip()
            self.root.after(0, lambda: self._handle_failure(detail))
            return

        self.root.after(0, lambda: self._handle_success(result, output_root))

    def _handle_success(self, result: dict[str, Any], output_root: Path) -> None:
        self.last_output_dir = output_root
        self.run_button.configure(state="normal")
        self.status_var.set("Spin cycle finished successfully.")
        self.progress_bar.configure(value=self.progress_bar.cget("maximum"))
        self.progress_text_var.set("Progress: 100%")
        self.append_output(format_run_summary(result))
        self.append_output("")
        self.append_output(json.dumps(result, indent=2, ensure_ascii=False))

    def _handle_failure(self, detail: str) -> None:
        self.run_button.configure(state="normal")
        self.status_var.set("Wash cycle stopped.")
        self.progress_text_var.set("Progress: stopped")
        self.append_output(f"Run failed: {detail}")
        messagebox.showerror("Washing Machine", detail)

    def _handle_progress_event(self, event: dict[str, Any]) -> None:
        current = int(event.get("current", 0) or 0)
        total = int(event.get("total", 1) or 1)
        if total < 1:
            total = 1
        current = max(0, min(current, total))

        self.progress_bar.configure(maximum=total, value=current)
        percent = int((current / total) * 100)
        message = str(event.get("message", "Running..."))
        self.status_var.set(message)
        self.progress_text_var.set(f"Progress: {percent}%")

    def open_output_folder(self) -> None:
        candidate = self.last_output_dir
        if candidate is None and self.output_var.get().strip():
            candidate = Path(self.output_var.get().strip())

        if candidate is None or not candidate.exists():
            messagebox.showinfo("Washing Machine", "No output folder is available yet.")
            return

        if sys.platform.startswith("win"):
            import os

            os.startfile(candidate)  # type: ignore[attr-defined]
        else:
            messagebox.showinfo("Washing Machine", f"Output folder: {candidate}")


def main() -> int:
    root = tk.Tk()
    WashingMachineApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
