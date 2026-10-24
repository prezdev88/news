from __future__ import annotations

import tkinter as tk
from dataclasses import replace
from tkinter import messagebox, ttk

from .config import AppError, remove_topic, rename_topic, source_topic, topic_name
from .theme import ACCENT, BORDER, INK, SOFT_ACCENT, SURFACE, center_dialog


class TopicsDialog(tk.Toplevel):
    def __init__(self, parent, settings, on_save):
        super().__init__(parent)
        self.settings = replace(settings)
        self.settings.validate()
        self.on_save = on_save
        self.title("Temas del periódico")
        self.transient(parent)
        self.resizable(False, False)
        self.configure(bg=SURFACE)
        content = ttk.Frame(self, padding=26)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="TU ACTUALIDAD", style="Section.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Label(content, text="Tus temas", style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(content, text="Crea o renombra categorías como Deportes, Cultura o Ciencia.", style="Muted.TLabel", wraplength=460).pack(anchor="w", pady=(6, 12))
        listing = ttk.Frame(content)
        listing.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(listing, height=9, width=53, exportselection=False, font="TkTextFont", relief="flat", borderwidth=0, highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT, background=SURFACE, foreground=INK, selectbackground=SOFT_ACCENT, selectforeground=ACCENT, selectborderwidth=0, activestyle="none")
        scrollbar = ttk.Scrollbar(listing, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.select_topic)
        ttk.Label(content, text="Nombre del tema", style="Muted.TLabel").pack(anchor="w", pady=(12, 5))
        self.name = tk.StringVar(self)
        ttk.Entry(content, textvariable=self.name).pack(fill="x")
        actions = ttk.Frame(content)
        actions.pack(fill="x", pady=(10, 12))
        ttk.Button(actions, text="Añadir", command=self.add).pack(side="left")
        ttk.Button(actions, text="Renombrar", command=self.rename).pack(side="left", padx=(6, 0))
        ttk.Button(actions, text="Eliminar", style="Danger.TButton", command=self.remove).pack(side="left", padx=(6, 0))
        ttk.Label(content, text="Al eliminar, reasignar las fuentes a:", style="Muted.TLabel").pack(anchor="w", pady=(0, 5))
        self.replacement = tk.StringVar(self)
        self.replacement_box = ttk.Combobox(content, textvariable=self.replacement, state="readonly")
        self.replacement_box.pack(fill="x")
        footer = ttk.Frame(content)
        footer.pack(fill="x", pady=(18, 0))
        ttk.Button(footer, text="Cancelar", command=self.close).pack(side="left")
        ttk.Button(footer, text="Guardar temas", command=self.save, style="Primary.TButton").pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _event: self.close())
        self.refresh(0)
        center_dialog(self, parent)
        self.grab_set()

    def selected_topic(self):
        selection = self.listbox.curselection()
        return self.settings.topics[selection[0]] if selection else None

    def refresh(self, index=0):
        self.listbox.delete(0, "end")
        for topic in self.settings.topics:
            count = sum(source_topic(source) == topic for source in self.settings.sources)
            self.listbox.insert("end", f"{topic}  ·  {count} fuentes")
        index = min(index, len(self.settings.topics) - 1)
        self.listbox.selection_set(index)
        self.listbox.see(index)
        self.select_topic()

    def select_topic(self, _event=None):
        current = self.selected_topic()
        if current is None:
            return
        self.name.set(current)
        choices = tuple(item for item in self.settings.topics if item != current)
        self.replacement_box.configure(values=choices)
        if self.replacement.get() not in choices:
            self.replacement.set("Nacionales" if "Nacionales" in choices else choices[0] if choices else "")

    def add(self):
        try:
            name = topic_name(self.name.get())
            settings = replace(self.settings, topics=(*self.settings.topics, name))
            settings.validate()
        except AppError as exc:
            messagebox.showerror("Añadir tema", str(exc), parent=self)
            return
        self.settings = settings
        self.refresh(settings.topics.index(name))

    def rename(self):
        current = self.selected_topic()
        if current is None:
            return
        try:
            settings = rename_topic(self.settings, current, self.name.get())
        except AppError as exc:
            messagebox.showerror("Renombrar tema", str(exc), parent=self)
            return
        index = settings.topics.index(topic_name(self.name.get()))
        self.settings = settings
        self.refresh(index)

    def remove(self):
        current = self.selected_topic()
        if current is None:
            return
        try:
            settings = remove_topic(self.settings, current, self.replacement.get())
        except AppError as exc:
            messagebox.showerror("Eliminar tema", str(exc), parent=self)
            return
        index = self.settings.topics.index(current)
        self.settings = settings
        self.refresh(index)

    def save(self):
        self.settings.validate()
        self.on_save(self.settings)
        self.close()

    def close(self):
        self.destroy()
        if self.master.winfo_exists():
            self.master.grab_set()
