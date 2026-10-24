from __future__ import annotations

import io
import math
import tkinter as tk
from tkinter import font, ttk

import cairo

BACKGROUND = "#f3f5f7"
SURFACE = "#ffffff"
INK = "#172b35"
MUTED = "#687985"
ACCENT = "#146c60"
ACCENT_HOVER = "#10584e"
SOFT_ACCENT = "#e8f3ef"
BORDER = "#dce4e8"
WORKSPACE = "#e7ecef"
ERROR = "#a83c45"


def rounded_surface(fill, stroke=None, *, size=32, radius=9, background=None):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    context = cairo.Context(surface)
    if background:
        context.set_source_rgb(*rgb(background))
        context.paint()
    inset = 0.5
    for x, y, start in (
        (size - radius - inset, radius + inset, -math.pi / 2),
        (size - radius - inset, size - radius - inset, 0),
        (radius + inset, size - radius - inset, math.pi / 2),
        (radius + inset, radius + inset, math.pi),
    ):
        context.arc(x, y, radius, start, start + math.pi / 2)
    context.close_path()
    context.set_source_rgb(*rgb(fill))
    context.fill_preserve()
    if stroke:
        context.set_source_rgb(*rgb(stroke))
        context.set_line_width(1)
        context.stroke()
    output = io.BytesIO()
    surface.write_to_png(output)
    return output.getvalue()


def rgb(color):
    return tuple(int(color[index:index + 2], 16) / 255 for index in (1, 3, 5))


def apply_theme(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    available = set(font.families(root))
    face = next((name for name in ("Inter", "Adwaita Sans", "Segoe UI", "DejaVu Sans") if name in available), "TkDefaultFont")
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        font.nametofont(name, root=root).configure(family=face, size=10)
    root.option_add("*TCombobox*Listbox.font", (face, 10))
    root.option_add("*TCombobox*Listbox.background", SURFACE)
    root.option_add("*TCombobox*Listbox.foreground", INK)
    root.option_add("*TCombobox*Listbox.selectBackground", SOFT_ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", ACCENT)
    root.configure(bg=BACKGROUND)
    images = []

    def image(fill, stroke=None, *, size=64, background=SURFACE):
        result = tk.PhotoImage(master=root, data=rounded_surface(fill, stroke, size=size, background=background), format="png")
        images.append(result)
        return result

    style.configure(".", font=(face, 10), background=SURFACE, foreground=INK)
    style.configure("TFrame", background=SURFACE)
    style.configure("App.TFrame", background=BACKGROUND)
    style.configure("TLabel", background=SURFACE, foreground=INK)
    style.configure("Muted.TLabel", foreground=MUTED, font=(face, 9))
    style.configure("AppMuted.TLabel", background=BACKGROUND, foreground=MUTED, font=(face, 9))
    style.configure("Heading.TLabel", font=(face, 14, "bold"))
    style.configure("DialogTitle.TLabel", font=(face, 21, "bold"))
    style.configure("Section.TLabel", font=(face, 9, "bold"), foreground=MUTED)
    style.configure("Badge.TLabel", background=SOFT_ACCENT, foreground=ACCENT, padding=(12, 7), font=(face, 9))
    style.configure("Connection.TLabel", background=BACKGROUND, foreground=MUTED, font=(face, 9))

    for name, fill, hover, pressed, foreground, stroke in (
        ("TButton", SURFACE, "#f2f6f5", "#e6eeeb", INK, BORDER),
        ("Primary.TButton", ACCENT, ACCENT_HOVER, "#0d493f", SURFACE, None),
        ("Quiet.TButton", SURFACE, "#f1f5f4", "#e6eeeb", ACCENT, None),
        ("Danger.TButton", SURFACE, "#fff0f0", "#ffe1e1", ERROR, BORDER),
    ):
        element = f"Manana.{name}.border"
        normal = image(fill, stroke)
        active = image(hover, stroke)
        down = image(pressed, stroke)
        disabled = image("#edf1f3", BORDER if stroke else None)
        focused = image(fill, ACCENT if foreground != SURFACE else "#72b9a9")
        style.element_create(element, "image", normal, ("disabled", disabled), ("pressed", down), ("active", active), ("focus", focused), border=10, padding=0, width=0, height=0, sticky="nsew")
        style.layout(name, [(element, {"sticky": "nsew", "children": [("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]})])
        style.configure(name, padding=(13, 9), foreground=foreground, font=(face, 9, "bold"), anchor="center", width=0)
        style.map(name, foreground=[("disabled", "#9ba8af")])
    style.configure("Primary.TButton", padding=(16, 12), font=(face, 10, "bold"))
    style.configure("Compact.TButton", padding=(10, 5))
    style.configure("Toolbar.TButton", padding=(10, 5))

    card = "Manana.card"
    # ttk tiles the image's center instead of stretching it. A large opaque tile
    # avoids thousands of small alpha composites when a card is repainted.
    style.element_create(card, "image", image(SURFACE, BORDER, size=128, background=BACKGROUND), border=12, padding=0, width=0, height=0, sticky="nsew")
    style.layout("Card.TFrame", [(card, {"sticky": "nsew"})])
    style.configure("Card.TFrame", background=BACKGROUND)
    style.configure("TEntry", fieldbackground=SURFACE, foreground=INK, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=(10, 8), relief="flat", insertcolor=INK)
    style.configure("TCombobox", fieldbackground=SURFACE, background="#f5f7f8", foreground=INK, arrowcolor=MUTED, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, arrowsize=12, padding=(9, 8))
    for name in ("TEntry", "TCombobox"):
        style.map(name, bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)], darkcolor=[("focus", ACCENT)])
    style.map("TCombobox", fieldbackground=[("readonly", SURFACE)], foreground=[("disabled", MUTED), ("readonly", INK)], selectbackground=[("!disabled", SURFACE)], selectforeground=[("!disabled", INK)])
    style.configure("TNotebook", background=SURFACE, borderwidth=0, tabmargins=(0, 0, 0, 12))
    style.configure("TNotebook.Tab", background=SURFACE, foreground=MUTED, padding=(13, 8), borderwidth=0, font=(face, 9, "bold"))
    style.map("TNotebook.Tab", background=[("selected", SOFT_ACCENT), ("active", "#f3f6f5")], foreground=[("selected", ACCENT), ("active", INK)])
    style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=INK, rowheight=38, borderwidth=0, font=(face, 10))
    style.configure("Treeview.Heading", background="#f4f7f8", foreground=MUTED, relief="flat", padding=(10, 10), font=(face, 9, "bold"))
    style.map("Treeview", background=[("selected", SOFT_ACCENT)], foreground=[("selected", ACCENT)])
    style.map("Treeview.Heading", background=[("active", "#edf2f3")])
    style.configure("TScrollbar", background="#c9d4da", troughcolor=SURFACE, borderwidth=0, arrowsize=12, relief="flat")
    style.configure("TSeparator", background=BORDER)
    style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor="#edf2f3", borderwidth=0, thickness=4)
    # Tcl holds image names; Python must retain the image objects for their lifetime.
    root._manana_theme_images = images
    return face


def document_icon(canvas, x, y, *, color=ACCENT, scale=1):
    def points(*values):
        return [coordinate * scale + (x if index % 2 == 0 else y) for index, coordinate in enumerate(values)]

    canvas.create_rectangle(*points(0, 0, 28, 34), outline=color, width=1.5)
    canvas.create_line(*points(6, 8, 22, 8), fill=color, width=2)
    canvas.create_rectangle(*points(6, 14, 12, 23), fill=color, outline="")
    for row in (14, 18, 22):
        canvas.create_line(*points(16, row, 22, row), fill=color, width=1)
    canvas.create_line(*points(6, 28, 22, 28), fill=color, width=1)


def center_dialog(window, parent):
    window.update_idletasks()
    width, height = window.winfo_width(), window.winfo_height()
    x = max(0, min(parent.winfo_rootx() + (parent.winfo_width() - width) // 2, window.winfo_screenwidth() - width))
    y = max(0, min(parent.winfo_rooty() + (parent.winfo_height() - height) // 2, window.winfo_screenheight() - height))
    window.geometry(f"+{x}+{y}")
