from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from manana.config import SOURCES, Settings, custom_source, load_settings, save_settings
from manana.lmstudio import LMStudio
from manana.printing import list_printers
from manana.sorting import alphabetical_key
from manana.source_dialog import SourcesDialog
from manana.topic_dialog import TopicsDialog


class AlphabeticalOrderingTests(unittest.TestCase):
    def test_spanish_labels_sort_without_case_or_accent_bias_and_keep_enye_after_n(self):
        labels = ["Zorro", "Ñandú", "Oasis", "Árbol", "nube", "Águila", "Economía"]
        self.assertEqual(sorted(labels, key=alphabetical_key), ["Águila", "Árbol", "Economía", "nube", "Ñandú", "Oasis", "Zorro"])

    def test_initial_sources_are_sorted_by_medium_then_topic(self):
        self.assertEqual([source.name for source in SOURCES], ["BioBioChile", "BioBioChile", "Cooperativa", "El Mostrador", "El Mostrador"])
        self.assertEqual([source.section for source in SOURCES[:2]], ["", "Tecnología"])

    def test_loaded_and_saved_choices_are_sorted_without_changing_defaults(self):
        settings = Settings(
            topics=("Zoología", "Árbol", "Nacionales", "Ciencia"),
            sources=(custom_source("Zeta", "https://zeta.example/feed"), custom_source("Águila", "https://aguila.example/feed")),
            printer="Zeta",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            save_settings(settings, path)
            loaded = load_settings(path)
            payload = json.loads(path.read_text())
        self.assertEqual(loaded.topics, ("Árbol", "Ciencia", "Nacionales", "Zoología"))
        self.assertEqual([source.name for source in loaded.sources], ["Águila", "Zeta"])
        self.assertEqual(payload["topics"], list(loaded.topics))
        self.assertEqual(loaded.printer, "Zeta")
        self.assertEqual(loaded.paper, "Carta")

    def test_models_are_sorted_and_the_explicit_choice_is_preserved(self):
        client = LMStudio(Settings(model="zeta"), session=Mock())
        response = {"data": [{"id": name} for name in ("zeta", "Águila", "gemma-4", "Beta", "embedding-model")]}
        with patch.object(client, "_request", return_value=response):
            self.assertEqual(client.models(), ["Águila", "Beta", "gemma-4", "zeta"])
            self.assertEqual(client.select_model(), "zeta")

    def test_printers_include_the_default_in_alphabetical_order(self):
        responses = [
            subprocess.CompletedProcess([], 0, "zeta\nÁguila\nCanon\nzeta\n", ""),
            subprocess.CompletedProcess([], 0, "system default destination: Beta\n", ""),
        ]
        with patch("manana.printing.subprocess.run", side_effect=responses):
            available = list_printers()
        self.assertEqual(available.names, ("Águila", "Beta", "Canon", "zeta"))
        self.assertEqual(available.default, "Beta")

    def test_source_selection_follows_the_same_source_when_its_row_moves(self):
        tree = Mock()
        tree.get_children.return_value = ()
        dialog = SimpleNamespace(
            sources=[custom_source("Zeta", "https://zeta.example/feed"), custom_source("Águila", "https://aguila.example/feed")],
            topics=["Zoología", "Árbol", "Ciencia"], tree=tree, update_actions=Mock(),
        )
        SourcesDialog.refresh(dialog, selected=0)
        self.assertEqual([source.name for source in dialog.sources], ["Águila", "Zeta"])
        self.assertEqual(dialog.topics, ["Árbol", "Ciencia", "Zoología"])
        tree.selection_set.assert_called_once_with("1")
        self.assertEqual(tree.insert.call_args_list[1].kwargs["values"][1], "Zeta")

    def test_added_and_renamed_topics_remain_selected_at_their_new_position(self):
        dialog = SimpleNamespace(settings=Settings(topics=("Ciencia", "Zoología"), sources=()), name=Mock(), refresh=Mock())
        dialog.name.get.return_value = "Árbol"
        TopicsDialog.add(dialog)
        self.assertEqual(dialog.settings.topics, ("Árbol", "Ciencia", "Zoología"))
        dialog.refresh.assert_called_once_with(0)

        dialog.refresh.reset_mock()
        dialog.name.get.return_value = "Biodiversidad"
        dialog.selected_topic = lambda: "Zoología"
        TopicsDialog.rename(dialog)
        self.assertEqual(dialog.settings.topics, ("Árbol", "Biodiversidad", "Ciencia"))
        dialog.refresh.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
