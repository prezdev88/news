from __future__ import annotations

import math
import queue
import sys
import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cairo

from .config import AppError, Settings, load_settings, save_settings
from .lmstudio import LMStudio
from .pipeline import generate, open_pdf
from .printing import list_printers, print_pdf
from .source_dialog import SourcesDialog

BACKGROUND = "#efeee8"
PAPER = "#ffffff"
INK = "#202923"
MUTED = "#626a63"
ACCENT = "#254c3c"
MIN_PREVIEW_ZOOM = 0.5
MAX_PREVIEW_ZOOM = 5.0


def preview_ppm(surface: cairo.ImageSurface) -> bytes:
    surface.flush()
    pixels = bytes(surface.get_data())
    rgb = bytearray(surface.get_width() * surface.get_height() * 3)
    # Cairo RGB24 stores native-endian 32-bit pixels; Tk's PPM accepts packed RGB.
    red, green, blue = (2, 1, 0) if sys.byteorder == "little" else (1, 2, 3)
    rgb[0::3] = pixels[red::4]
    rgb[1::3] = pixels[green::4]
    rgb[2::3] = pixels[blue::4]
    return f"P6\n{surface.get_width()} {surface.get_height()}\n255\n".encode("ascii") + rgb


class NewspaperApp:
    def __init__(self, root: tk.Tk, settings: Settings):
        self.root = root
        self.settings = settings
        self.events = queue.Queue()
        self.busy = False
        self.latest_pdf = None
        self.preview_image = None
        self.preview_item = None
        self.preview_surface = None
        self.preview_render_job = None
        self.preview_refine_job = None
        self.preview_zoom = 1.0
        self.preview_offset = (0.0, 0.0)
        self.preview_drag_point = None
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
        style.configure("Compact.TButton", padding=(8, 3))
        style.configure("Primary.TButton", background=ACCENT, foreground="white", padding=(18, 13), font=("DejaVu Sans", 11, "bold"))
        style.map("Primary.TButton", background=[("active", "#35664e"), ("disabled", "#8b9990")])
        outer = ttk.Frame(self.root, padding=28)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="TU PERIÓDICO · A TU RITMO", font=("DejaVu Sans", 9, "bold"), foreground=ACCENT).pack(anchor="w")
        ttk.Label(outer, text="La Mañana", font=("Liberation Serif", 38, "bold")).pack(anchor="w", pady=(4, 0))
        ttk.Label(outer, text="Actualidad y tecnología de Chile, resumidas en tu equipo y listas en una página.", style="Muted.TLabel").pack(anchor="w", pady=(4, 22))
        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body, width=400)
        left.pack(side="left", fill="y", padx=(0, 26))
        left.pack_propagate(False)
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)
        preview_tools = ttk.Frame(right)
        preview_tools.pack(fill="x", pady=(0, 8))
        self.zoom_status = tk.StringVar(value="Zoom 100% · Rueda: zoom · Arrastra: mover")
        ttk.Label(preview_tools, textvariable=self.zoom_status, style="Muted.TLabel").pack(side="left")
        self.reset_zoom_button = ttk.Button(preview_tools, text="Ajustar página", command=self.reset_preview_zoom, state="disabled")
        self.reset_zoom_button.pack(side="right")
        self.preview = tk.Canvas(right, bg="#dedfd7", highlightthickness=0, width=1, height=1)
        self.preview.pack(fill="both", expand=True)
        self.preview.bind("<Configure>", self.schedule_preview_draw)
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.preview.bind(sequence, self.zoom_preview)
        self.preview.bind("<ButtonPress-1>", self.start_preview_drag)
        self.preview.bind("<B1-Motion>", self.drag_preview)
        self.preview.bind("<ButtonRelease-1>", self.end_preview_drag)
        self.preview.bind("<Double-Button-1>", self.reset_preview_zoom)
        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=(12, 0))
        self.open_button = ttk.Button(actions, text="Abrir PDF", command=self.open_latest, state="disabled")
        self.open_button.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.print_button = ttk.Button(actions, text="Imprimir PDF…", command=self.start_printing, state="disabled")
        self.print_button.pack(side="left", fill="x", expand=True)
        ttk.Label(left, text="01   TU MODELO LOCAL", font=("DejaVu Sans", 9, "bold")).pack(anchor="w", pady=(0, 12))
        self.entry(left, "Servidor de LM Studio", "base_url", self.settings.base_url)
        model_row = ttk.Frame(left)
        model_row.pack(fill="x", pady=(4, 12))
        ttk.Label(model_row, text="Modelo").pack(anchor="w", pady=(0, 5))
        self.fields["model"] = tk.StringVar(value=self.settings.model)
        self.model_box = ttk.Combobox(model_row, textvariable=self.fields["model"], width=16)
        self.model_box.pack(side="left", fill="x", expand=True)
        self.discover_button = ttk.Button(model_row, text="Detectar", command=self.discover)
        self.discover_button.pack(side="right", padx=(8, 0))
        edition_header = ttk.Frame(left)
        edition_header.pack(fill="x", pady=(12, 8))
        ttk.Label(edition_header, text="02   TU EDICIÓN", font=("DejaVu Sans", 9, "bold")).pack(side="left")
        self.sources_button = ttk.Button(edition_header, text=f"Fuentes ({len(self.settings.active_sources)})…", style="Compact.TButton", command=self.manage_sources)
        self.sources_button.pack(side="right")
        options = ttk.Frame(left)
        options.pack(fill="x")
        for key, title, value, values in (
            ("paper", "Papel", self.settings.paper, ("A4", "Carta")),
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
        ttk.Label(left, textvariable=self.status, style="Muted.TLabel", wraplength=400).pack(fill="x")
        self.log = tk.Text(left, width=1, height=7, bg="#e6e7df", fg=INK, font=("DejaVu Sans Mono", 8), relief="flat", padx=10, pady=10, state="disabled", wrap="word")
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

    def manage_sources(self):
        if self.busy:
            return

        def apply(sources, topics=None):
            settings = replace(self.read_settings(), sources=sources, topics=topics if topics is not None else self.settings.topics)
            save_settings(settings)
            self.settings = settings
            self.sources_button.configure(text=f"Fuentes ({len(settings.active_sources)})…")
            self.status.set(f"Fuentes guardadas: {len(settings.active_sources)} secciones activas.")

        SourcesDialog(self.root, self.settings.sources, apply, topics=self.settings.topics)

    def set_busy(self, value):
        self.busy = value
        state = "disabled" if value else "normal"
        self.generate_button.configure(state=state)
        self.discover_button.configure(state=state)
        self.sources_button.configure(state=state)
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
        self.preview_surface = cairo.ImageSurface.create_from_png(str(path))
        self.reset_preview_zoom()

    def reset_preview_zoom(self, _event=None):
        self.preview_zoom = 1.0
        self.preview_offset = (0.0, 0.0)
        self.preview_drag_point = None
        self.draw_preview()
        return "break"

    def preview_geometry(self):
        width, height = self.preview.winfo_width(), self.preview.winfo_height()
        original = self.preview_surface
        fit_scale = min(max(1, width - 32) / original.get_width(), max(1, height - 32) / original.get_height())
        scale = fit_scale * self.preview_zoom
        page_width, page_height = original.get_width() * scale, original.get_height() * scale
        center_x, center_y = (width - page_width) / 2, (height - page_height) / 2
        left = min(16, max(width - 16 - page_width, center_x + self.preview_offset[0])) if page_width > width - 32 else center_x
        top = min(16, max(height - 16 - page_height, center_y + self.preview_offset[1])) if page_height > height - 32 else center_y
        self.preview_offset = (left - center_x, top - center_y)
        return width, height, scale, left, top

    def zoom_preview(self, event):
        if self.preview_surface is None:
            return "break"
        if getattr(event, "num", None) in (4, 5):
            steps = 1 if event.num == 4 else -1
        else:
            delta = getattr(event, "delta", 0)
            steps = delta if self.root.tk.call("tk", "windowingsystem") == "aqua" else delta / 120
        if not steps:
            return "break"
        width, height, scale, left, top = self.preview_geometry()
        zoom = min(MAX_PREVIEW_ZOOM, max(MIN_PREVIEW_ZOOM, self.preview_zoom * 1.2 ** max(-4, min(4, steps))))
        if zoom == self.preview_zoom:
            return "break"
        factor = zoom / self.preview_zoom
        # Keep the same point of the page underneath the pointer while zooming.
        new_left = event.x - (event.x - left) * factor
        new_top = event.y - (event.y - top) * factor
        new_width = self.preview_surface.get_width() * scale * factor
        new_height = self.preview_surface.get_height() * scale * factor
        self.preview_zoom = zoom
        self.preview_offset = (new_left - (width - new_width) / 2, new_top - (height - new_height) / 2)
        self.schedule_preview_draw()
        return "break"

    def start_preview_drag(self, event):
        if self.preview_surface is not None:
            self.preview_drag_point = (event.x, event.y)
            self.preview.configure(cursor="fleur")
        return "break"

    def drag_preview(self, event):
        if self.preview_drag_point is not None:
            self.preview_offset = (
                self.preview_offset[0] + event.x - self.preview_drag_point[0],
                self.preview_offset[1] + event.y - self.preview_drag_point[1],
            )
            self.preview_drag_point = (event.x, event.y)
            self.schedule_preview_draw()
        return "break"

    def end_preview_drag(self, _event):
        self.preview_drag_point = None
        self.preview.configure(cursor="hand2" if self.preview_surface is not None else "")
        return "break"

    def schedule_preview_draw(self, _event=None):
        if self.preview_refine_job is not None:
            self.root.after_cancel(self.preview_refine_job)
            self.preview_refine_job = None
        # Combine events into the next frame instead of rendering every wheel tick.
        if self.preview_render_job is None:
            self.preview_render_job = self.root.after(16, lambda: self.draw_preview(interactive=True))
        if self.preview_surface is not None:
            self.preview_refine_job = self.root.after(150, self.draw_preview)

    def draw_preview(self, *, interactive=False):
        if self.preview_render_job is not None:
            self.root.after_cancel(self.preview_render_job)
            self.preview_render_job = None
        if not interactive and self.preview_refine_job is not None:
            self.root.after_cancel(self.preview_refine_job)
            self.preview_refine_job = None
        width, height = self.preview.winfo_width(), self.preview.winfo_height()
        if width <= 32 or height <= 32:
            return
        self.zoom_status.set(f"Zoom {self.preview_zoom:.0%} · Rueda: zoom · Arrastra: mover")
        self.reset_zoom_button.configure(state="normal" if self.preview_surface is not None else "disabled")
        self.preview.configure(cursor="fleur" if self.preview_drag_point else "hand2" if self.preview_surface is not None else "")
        if self.preview_surface is None:
            self.preview.delete("all")
            self.preview_item = None
            self.preview_image = None
            center_x, center_y = width / 2, height / 2
            text_width = min(320, width - 40)
            self.preview.create_text(center_x, center_y - 80, text="La Mañana", font=("Liberation Serif", 30, "bold"), fill=INK)
            self.preview.create_line(center_x - text_width / 2, center_y - 30, center_x + text_width / 2, center_y - 30, fill=MUTED)
            message = "PDF disponible para abrir o imprimir." if self.latest_pdf else "Tu próxima edición aparecerá aquí"
            self.preview.create_text(center_x, center_y + 15, width=text_width, text=message, font=("DejaVu Sans", 12), fill=MUTED)
            self.preview.create_text(center_x, center_y + 70, width=text_width, text="PDF de una página\nA4 o Carta · Fuentes consultables", font=("DejaVu Sans", 10), fill=MUTED)
            return
        original = self.preview_surface
        width, height, scale, left, top = self.preview_geometry()
        image_left, image_top = max(0, math.floor(left)), max(0, math.floor(top))
        image_width = min(width, math.ceil(left + original.get_width() * scale)) - image_left
        image_height = min(height, math.ceil(top + original.get_height() * scale)) - image_top
        # Render only the visible part of the page, keeping memory bounded at any zoom.
        resized = cairo.ImageSurface(cairo.FORMAT_RGB24, image_width, image_height)
        context = cairo.Context(resized)
        context.set_source_rgb(1, 1, 1)
        context.paint()
        context.translate(left - image_left, top - image_top)
        context.scale(scale, scale)
        context.set_source_surface(original)
        context.get_source().set_filter(cairo.FILTER_BILINEAR if interactive else cairo.FILTER_BEST)
        context.paint()
        image = tk.PhotoImage(data=preview_ppm(resized), format="PPM", master=self.root)
        if self.preview_item is None:
            self.preview.delete("all")
            self.preview_item = self.preview.create_image(image_left, image_top, image=image, anchor="nw")
        else:
            self.preview.coords(self.preview_item, image_left, image_top)
            self.preview.itemconfigure(self.preview_item, image=image)
        self.preview_image = image

    def load_pdf(self, path):
        self.latest_pdf = Path(path)
        self.open_button.configure(state="normal")
        self.print_button.configure(state="disabled" if self.busy else "normal")
        self.preview_surface = None
        preview = self.latest_pdf.with_suffix(".png")
        if preview.is_file():
            try:
                self.show_preview(preview)
                return
            except (tk.TclError, cairo.Error, OSError):
                self.preview_surface = None
        self.reset_preview_zoom()

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
        ttk.Combobox(content, textvariable=paper, values=("A4", "Carta (Letter)"), state="readonly").pack(fill="x")
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
