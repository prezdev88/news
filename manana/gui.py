from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .config import AppError, Settings, load_settings, save_settings
from .lmstudio import LMStudio
from .pipeline import generate, open_pdf
from .printing import list_printers, print_pdf

BACKGROUND = "#efeee8"
PAPER = "#ffffff"
INK = "#202923"
MUTED = "#626a63"
ACCENT = "#254c3c"


class NewspaperApp:
    def __init__(self, root: tk.Tk, settings: Settings):
        self.root = root
        self.settings = settings
        self.events = queue.Queue()
        self.busy = False
        self.latest_pdf = None
        self.preview_image = None
        self.fields = {}
        root.title("La Mañana · Tu periódico local")
        root.geometry("1100x800")
        root.minsize(920, 720)
        root.configure(bg=BACKGROUND)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._build()
        root.after(100, self.poll)
        root.after(150, self.restore_latest_pdf)
        # Model discovery is deliberately read-only: opening the app does not
        # download models, fetch news or start inference.
        root.after(250, self.discover)

    def _build(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=BACKGROUND)
        style.configure("TLabel", background=BACKGROUND, foreground=INK, font=("DejaVu Sans", 10))
        style.configure("Muted.TLabel", foreground=MUTED, font=("DejaVu Sans", 9))
        style.configure("TEntry", padding=8, fieldbackground=PAPER)
        style.configure("TCombobox", padding=7, fieldbackground=PAPER)
        style.configure("TButton", padding=(12, 9), font=("DejaVu Sans", 9))
        style.configure("Primary.TButton", background=ACCENT, foreground="white", padding=(18, 13), font=("DejaVu Sans", 11, "bold"))
        style.map("Primary.TButton", background=[("active", "#35664e"), ("disabled", "#8b9990")])
        outer = ttk.Frame(self.root, padding=28)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="TU PERIÓDICO · A TU RITMO", font=("DejaVu Sans", 9, "bold"), foreground=ACCENT).pack(anchor="w")
        ttk.Label(outer, text="La Mañana", font=("Liberation Serif", 38, "bold")).pack(anchor="w", pady=(4, 0))
        ttk.Label(outer, text="Actualidad y tecnología de Chile, resumidas en tu equipo y listas en una página.", style="Muted.TLabel").pack(anchor="w", pady=(4, 22))
        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True, padx=(0, 26))
        right = ttk.Frame(body, width=400)
        right.pack(side="right", fill="both")
        right.pack_propagate(False)
        self.preview = tk.Canvas(right, bg="#dedfd7", highlightthickness=0, width=400, height=565)
        self.preview.pack(fill="both", expand=True)
        self.preview.create_text(200, 165, text="La Mañana", font=("Liberation Serif", 30, "bold"), fill=INK)
        self.preview.create_line(50, 220, 350, 220, fill=MUTED)
        self.preview.create_text(200, 263, width=290, text="Tu próxima edición aparecerá aquí", font=("DejaVu Sans", 12), fill=MUTED)
        self.preview.create_text(200, 310, width=290, text="PDF de una página\nA4 o Carta · Fuentes consultables", font=("DejaVu Sans", 10), fill=MUTED)
        self.open_button = ttk.Button(right, text="Abrir PDF", command=self.open_latest, state="disabled")
        self.open_button.pack(fill="x", pady=(12, 0))
        self.print_button = ttk.Button(right, text="Imprimir PDF…", command=self.start_printing, state="disabled")
        self.print_button.pack(fill="x", pady=(8, 0))
        ttk.Label(left, text="01   TU MODELO LOCAL", font=("DejaVu Sans", 9, "bold")).pack(anchor="w", pady=(0, 12))
        self.entry(left, "Servidor de LM Studio", "base_url", self.settings.base_url)
        model_row = ttk.Frame(left)
        model_row.pack(fill="x", pady=(4, 12))
        ttk.Label(model_row, text="Modelo").pack(anchor="w", pady=(0, 5))
        self.fields["model"] = tk.StringVar(value=self.settings.model)
        self.model_box = ttk.Combobox(model_row, textvariable=self.fields["model"])
        self.model_box.pack(side="left", fill="x", expand=True)
        self.discover_button = ttk.Button(model_row, text="Detectar", command=self.discover)
        self.discover_button.pack(side="right", padx=(8, 0))
        ttk.Label(left, text="02   TU EDICIÓN", font=("DejaVu Sans", 9, "bold")).pack(anchor="w", pady=(12, 12))
        options = ttk.Frame(left)
        options.pack(fill="x")
        for key, title, value, values in (
            ("paper", "Papel", self.settings.paper, ("Carta", "A4")),
            ("article_count", "Noticias", str(self.settings.article_count), ("3", "4", "5", "6", "7")),
            ("lookback_hours", "Últimas horas", str(self.settings.lookback_hours), ("12", "24", "48", "72")),
        ):
            column = ttk.Frame(options)
            column.pack(side="left", fill="x", expand=True, padx=(0, 10))
            ttk.Label(column, text=title, style="Muted.TLabel").pack(anchor="w", pady=(0, 5))
            self.fields[key] = tk.StringVar(value=value)
            ttk.Combobox(column, textvariable=self.fields[key], values=values, state="readonly", width=9).pack(fill="x")
        self.entry(left, "Carpeta de salida", "output_dir", self.settings.output_dir)
        ttk.Button(left, text="Elegir carpeta…", command=self.choose_directory).pack(anchor="w", pady=(0, 12))
        self.generate_button = ttk.Button(left, text="Generar mi periódico", style="Primary.TButton", command=self.start_generation)
        self.generate_button.pack(fill="x", pady=(6, 10))
        self.progress = ttk.Progressbar(left, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 9))
        self.status = tk.StringVar(value="Carga un modelo en LM Studio y activa Developer → Start Server.")
        ttk.Label(left, textvariable=self.status, style="Muted.TLabel", wraplength=480).pack(anchor="w")
        self.log = tk.Text(left, height=7, bg="#e6e7df", fg=INK, font=("DejaVu Sans Mono", 8), relief="flat", padx=10, pady=10, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, pady=(12, 0))
        ttk.Label(outer, text="Internet para leer los medios · Resúmenes con LM Studio · Cada edición conserva sus fuentes", style="Muted.TLabel").pack(anchor="w", pady=(18, 0))

    def entry(self, parent, label, key, value):
        ttk.Label(parent, text=label, style="Muted.TLabel").pack(anchor="w", pady=(10, 5))
        self.fields[key] = tk.StringVar(value=value)
        ttk.Entry(parent, textvariable=self.fields[key]).pack(fill="x", pady=(0, 8))

    def read_settings(self):
        try:
            result = replace(self.settings, **{key: (int(var.get()) if key in {"article_count", "lookback_hours"} else var.get()) for key, var in self.fields.items()})
            result.validate()
            return result
        except (ValueError, TypeError) as exc:
            raise AppError("Revisa los valores de noticias y horas.") from exc

    def choose_directory(self):
        directory = filedialog.askdirectory(parent=self.root, initialdir=self.fields["output_dir"].get(), title="Dónde guardar tu periódico")
        if directory:
            self.fields["output_dir"].set(directory)

    def set_busy(self, value):
        self.busy = value
        state = "disabled" if value else "normal"
        self.generate_button.configure(state=state)
        self.discover_button.configure(state=state)
        self.print_button.configure(state="normal" if self.latest_pdf and not value else "disabled")
        if value:
            self.progress.start(12)
        else:
            self.progress.stop()

    def discover(self):
        if self.busy:
            return
        try:
            settings = self.read_settings()
        except AppError as exc:
            self.status.set(str(exc))
            return
        self.set_busy(True)
        self.status.set("Buscando los modelos disponibles en LM Studio…")

        def worker():
            try:
                models = LMStudio(settings).models()
                self.events.put(("models", models))
            except AppError as exc:
                self.events.put(("connection_error", str(exc)))
            finally:
                self.events.put(("idle", None))

        threading.Thread(target=worker, daemon=True).start()

    def start_generation(self):
        if self.busy:
            return
        try:
            settings = self.read_settings()
            save_settings(settings)
            self.settings = settings
        except (AppError, OSError) as exc:
            messagebox.showerror("Revisa la configuración", str(exc), parent=self.root)
            return
        self.set_busy(True)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

        def worker():
            try:
                path = generate(settings, lambda text: self.events.put(("progress", text)))
                self.events.put(("done", path))
            except Exception as exc:
                self.events.put(("error", str(exc)))
            finally:
                self.events.put(("idle", None))

        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "models":
                    self.model_box.configure(values=value)
                    if not self.fields["model"].get() or self.fields["model"].get() not in value:
                        gemma = [name for name in value if "gemma" in name.lower()]
                        choice = gemma[0] if len(gemma) == 1 else value[0] if len(value) == 1 else ""
                        self.fields["model"].set(choice)
                    self.status.set(f"{len(value)} modelos disponibles. Elige uno y genera tu edición.")
                elif kind == "progress":
                    self.status.set(value)
                    self.log.configure(state="normal")
                    self.log.insert("end", value + "\n")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                elif kind == "done":
                    self.load_pdf(value)
                    self.status.set(f"Tu periódico de {self.settings.article_count} noticias está listo: {value.name}")
                elif kind == "printers":
                    self.show_print_dialog(value)
                elif kind == "printed":
                    self.status.set(value.message)
                elif kind == "print_error":
                    self.status.set(value)
                    messagebox.showerror("Imprimir periódico", value, parent=self.root)
                elif kind in {"error", "connection_error"}:
                    self.status.set(value)
                    if kind == "error":
                        messagebox.showerror("No se pudo generar la edición", value, parent=self.root)
                elif kind == "idle":
                    self.set_busy(False)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def show_preview(self, path):
        original = tk.PhotoImage(file=str(path))
        factor = max(1, (original.width() + 389) // 390, (original.height() + 549) // 550)
        self.preview_image = original.subsample(factor)
        self.preview.delete("all")
        self.preview.create_image(200, 12, image=self.preview_image, anchor="n")

    def load_pdf(self, path):
        self.latest_pdf = Path(path)
        self.open_button.configure(state="normal")
        self.print_button.configure(state="disabled" if self.busy else "normal")
        preview = self.latest_pdf.with_suffix(".png")
        if preview.is_file():
            try:
                self.show_preview(preview)
            except tk.TclError:
                self.preview.delete("all")
                self.preview.create_text(200, 200, width=300, text="PDF disponible para abrir o imprimir.", fill=MUTED)

    def restore_latest_pdf(self):
        try:
            files = list(Path(self.settings.output_dir).expanduser().glob("la-manana-*.pdf"))
            if files:
                path = max(files, key=lambda item: item.stat().st_mtime)
                self.load_pdf(path)
                self.status.set(f"Última edición guardada: {path.name}")
        except OSError:
            pass

    def start_printing(self):
        if self.busy or not self.latest_pdf:
            return
        self.set_busy(True)
        self.status.set("Buscando las impresoras disponibles…")

        def worker():
            try:
                self.events.put(("printers", list_printers()))
            except AppError as exc:
                self.events.put(("print_error", str(exc)))
            finally:
                self.events.put(("idle", None))

        threading.Thread(target=worker, daemon=True).start()

    def show_print_dialog(self, available):
        path = self.latest_pdf
        dialog = tk.Toplevel(self.root)
        dialog.title("Imprimir periódico")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.configure(bg=BACKGROUND)
        content = ttk.Frame(dialog, padding=22)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="Imprimir tu periódico", font=("Liberation Serif", 23, "bold")).pack(anchor="w")
        ttk.Label(content, text=path.name, style="Muted.TLabel", wraplength=390).pack(anchor="w", pady=(5, 18))
        selected = self.settings.printer if self.settings.printer in available.names else available.default or available.names[0]
        printer = tk.StringVar(value=selected)
        ttk.Label(content, text="Impresora").pack(anchor="w", pady=(0, 5))
        ttk.Combobox(content, textvariable=printer, values=available.names, state="readonly", width=43).pack(fill="x")
        paper = tk.StringVar(value="Carta (Letter)" if self.fields["paper"].get() == "Carta" else "A4")
        ttk.Label(content, text="Papel").pack(anchor="w", pady=(13, 5))
        ttk.Combobox(content, textvariable=paper, values=("Carta (Letter)", "A4"), state="readonly").pack(fill="x")
        ttk.Label(content, text="Blanco y negro · Una cara · Una copia", style="Muted.TLabel").pack(anchor="w", pady=(14, 18))
        buttons = ttk.Frame(content)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancelar", command=dialog.destroy).pack(side="left")

        def submit():
            destination = printer.get()
            size = "Carta" if paper.get() == "Carta (Letter)" else "A4"
            dialog.destroy()
            self.queue_print(path, destination, size)

        ttk.Button(buttons, text="Imprimir en negro", style="Primary.TButton", command=submit).pack(side="right")
        dialog.grab_set()

    def queue_print(self, path, printer, paper):
        if self.busy:
            return
        try:
            self.fields["paper"].set(paper)
            self.settings = replace(self.read_settings(), printer=printer)
            save_settings(self.settings)
        except (AppError, OSError) as exc:
            messagebox.showerror("Imprimir periódico", str(exc), parent=self.root)
            return
        self.set_busy(True)
        self.status.set(f"Enviando una copia a {printer}, en {paper} y blanco y negro…")

        def worker():
            try:
                self.events.put(("printed", print_pdf(path, printer=printer, paper=paper)))
            except AppError as exc:
                self.events.put(("print_error", str(exc)))
            finally:
                self.events.put(("idle", None))

        threading.Thread(target=worker, daemon=True).start()

    def open_latest(self):
        if self.latest_pdf:
            try:
                open_pdf(self.latest_pdf)
            except AppError as exc:
                messagebox.showerror("Abrir PDF", str(exc), parent=self.root)

    def close(self):
        try:
            save_settings(self.read_settings())
        except (AppError, OSError):
            pass
        self.root.destroy()


def launch(settings=None):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise AppError("No se pudo abrir la ventana. Ejecuta la app desde tu sesión gráfica o usa ./generar.sh desde la terminal.") from exc
    NewspaperApp(root, settings or load_settings())
    root.mainloop()
