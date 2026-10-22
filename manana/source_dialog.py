from __future__ import annotations

import tkinter as tk
from dataclasses import replace
from tkinter import messagebox, ttk

from .config import AppError, DEFAULT_TOPICS, SOURCES, Settings, custom_source, source_sort_key, source_topic
from .sorting import alphabetical_key
from .topic_dialog import TopicsDialog


class SourcesDialog(tk.Toplevel):
    def __init__(self, parent, sources, on_save, *, topics=DEFAULT_TOPICS):
        settings = Settings(sources=tuple(sources), topics=tuple(topics))
        settings.validate()
        super().__init__(parent)
        self.sources = list(settings.sources)
        self.topics = list(settings.topics)
        self.on_save = on_save
        self.title("Fuentes de noticias")
        self.transient(parent)
        self.geometry("800x510")
        self.minsize(640, 420)
        self.configure(bg=parent.cget("bg"))
        content = ttk.Frame(self, padding=22)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="Tus fuentes de noticias", font=("Liberation Serif", 24, "bold")).pack(anchor="w")
        ttk.Label(
            content, text="Marca los medios que quieres consultar. Puedes añadir una sección de noticias o un enlace RSS/Atom.",
            style="Muted.TLabel", wraplength=580,
        ).pack(anchor="w", pady=(6, 14))
        table = ttk.Frame(content)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("enabled", "name", "section", "url"), show="headings", selectmode="browse", height=8)
        for name, title, width in (("enabled", "Usar", 50), ("name", "Medio", 150), ("section", "Tema", 100), ("url", "URL", 380)):
            self.tree.heading(name, text=title)
            self.tree.column(name, width=width, minwidth=45 if name == "enabled" else 80, stretch=name == "url")
        self.tree.column("enabled", anchor="center")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Button-1>", self.click_source)
        self.tree.bind("<space>", self.toggle_source)
        self.tree.bind("<Double-1>", self.double_click_source)
        self.tree.bind("<<TreeviewSelect>>", self.update_actions)
        actions = ttk.Frame(content)
        actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="Añadir…", command=self.edit_source).pack(side="left")
        self.toggle_button = ttk.Button(actions, text="Activar / desactivar", command=self.toggle_source)
        self.toggle_button.pack(side="left", padx=(6, 0))
        self.edit_button = ttk.Button(actions, text="Editar…", command=self.edit_selected)
        self.edit_button.pack(side="left", padx=(6, 0))
        self.delete_button = ttk.Button(actions, text="Eliminar", command=self.delete_source)
        self.delete_button.pack(side="left", padx=(6, 0))
        ttk.Button(actions, text="Temas…", command=self.manage_topics).pack(side="right")
        ttk.Button(content, text="Restaurar fuentes iniciales", command=self.restore_defaults).pack(anchor="w", pady=(10, 0))
        footer = ttk.Frame(content)
        footer.pack(fill="x", pady=(16, 0))
        ttk.Button(footer, text="Cancelar", command=self.destroy).pack(side="left")
        ttk.Button(footer, text="Guardar fuentes", command=self.save, style="Primary.TButton").pack(side="right")
        self.refresh()
        self.grab_set()

    def selected_index(self):
        selection = self.tree.selection()
        return int(selection[0]) if selection else None

    def refresh(self, selected=None):
        selected_url = self.sources[min(selected, len(self.sources) - 1)].url if selected is not None and self.sources else None
        self.sources.sort(key=source_sort_key)
        self.topics.sort(key=alphabetical_key)
        self.tree.delete(*self.tree.get_children())
        for index, source in enumerate(self.sources):
            self.tree.insert("", "end", iid=str(index), values=("☑" if source.enabled else "☐", source.name, source_topic(source), source.url))
        if selected_url is not None:
            item = str(next(index for index, source in enumerate(self.sources) if source.url == selected_url))
            self.tree.selection_set(item)
            self.tree.focus(item)
            self.tree.see(item)
        self.update_actions()

    def update_actions(self, _event=None):
        state = "normal" if self.selected_index() is not None else "disabled"
        for button in (self.toggle_button, self.edit_button, self.delete_button):
            button.configure(state=state)

    def click_source(self, event):
        item = self.tree.identify_row(event.y)
        if item and self.tree.identify_column(event.x) == "#1":
            self.tree.selection_set(item)
            return self.toggle_source()

    def double_click_source(self, event):
        if self.tree.identify_row(event.y) and self.tree.identify_column(event.x) != "#1":
            self.edit_selected()
        return "break"

    def toggle_source(self, _event=None):
        index = self.selected_index()
        if index is not None:
            self.sources[index] = replace(self.sources[index], enabled=not self.sources[index].enabled)
            self.refresh(index)
        return "break"

    def delete_source(self):
        index = self.selected_index()
        if index is not None:
            self.sources.pop(index)
            self.refresh(index)

    def restore_defaults(self):
        for default in SOURCES:
            index = next((index for index, source in enumerate(self.sources) if source.url.rstrip("/") == default.url.rstrip("/")), None)
            if index is None:
                self.sources.append(default)
            else:
                self.sources[index] = default
        settings = Settings(sources=tuple(self.sources), topics=tuple(self.topics))
        settings.validate()
        self.sources = list(settings.sources)
        self.topics = list(settings.topics)
        self.refresh(0)

    def edit_selected(self):
        index = self.selected_index()
        if index is not None:
            self.edit_source(index)

    def manage_topics(self):
        settings = Settings(sources=tuple(self.sources), topics=tuple(self.topics))
        settings.validate()

        def apply(updated):
            self.sources = list(updated.sources)
            self.topics = list(updated.topics)
            self.refresh()

        TopicsDialog(self, settings, apply)

    def edit_source(self, index=None):
        previous = self.sources[index] if index is not None else None
        editor = tk.Toplevel(self)
        editor.title("Editar fuente" if previous else "Añadir fuente")
        editor.transient(self)
        editor.resizable(False, False)
        editor.configure(bg=self.cget("bg"))
        content = ttk.Frame(editor, padding=22)
        content.pack(fill="both", expand=True)
        name = tk.StringVar(editor, value=previous.name if previous else "")
        url = tk.StringVar(editor, value=previous.url if previous else "")
        default_topic = "Nacionales" if "Nacionales" in self.topics else self.topics[0]
        section = tk.StringVar(editor, value=source_topic(previous) if previous else default_topic)
        ttk.Label(content, text="Nombre del medio").pack(anchor="w")
        name_entry = ttk.Entry(content, textvariable=name, width=57)
        name_entry.pack(fill="x", pady=(5, 12))
        ttk.Label(content, text="URL de sección o RSS/Atom").pack(anchor="w")
        ttk.Entry(content, textvariable=url).pack(fill="x", pady=(5, 12))
        ttk.Label(content, text="Tema (elige o escribe uno nuevo)").pack(anchor="w")
        ttk.Combobox(content, textvariable=section, values=self.topics).pack(fill="x", pady=(5, 12))
        ttk.Label(
            content, text="Usa una sección o RSS que publique el tema elegido. La app filtra las fuentes nuevas por fecha, texto accesible y relación con Chile.",
            style="Muted.TLabel", wraplength=460,
        ).pack(anchor="w", pady=(0, 16))
        buttons = ttk.Frame(content)
        buttons.pack(fill="x")

        def close_editor():
            editor.destroy()
            if self.winfo_exists():
                self.grab_set()

        def accept():
            try:
                source = custom_source(name.get(), url.get(), section.get(), previous)
                draft = list(self.sources)
                if index is None:
                    draft.append(source)
                else:
                    draft[index] = source
                settings = Settings(sources=tuple(draft), topics=tuple(self.topics))
                settings.validate()
            except AppError as exc:
                messagebox.showerror("Revisa la fuente", str(exc), parent=editor)
                return
            self.sources = list(settings.sources)
            self.topics = list(settings.topics)
            selected_index = next(index for index, item in enumerate(self.sources) if item.url == source.url)
            self.refresh(selected_index)
            close_editor()

        ttk.Button(buttons, text="Cancelar", command=close_editor).pack(side="left")
        ttk.Button(buttons, text="Guardar fuente", command=accept, style="Primary.TButton").pack(side="right")
        editor.protocol("WM_DELETE_WINDOW", close_editor)
        editor.grab_set()
        name_entry.focus_set()

    def save(self):
        try:
            settings = Settings(sources=tuple(self.sources), topics=tuple(self.topics))
            settings.validate()
            if not settings.active_sources:
                raise AppError("Activa al menos una fuente para preparar tu periódico.")
            self.on_save(settings.sources, settings.topics)
        except (AppError, OSError) as exc:
            messagebox.showerror("Guardar fuentes", str(exc), parent=self)
            return
        self.destroy()
