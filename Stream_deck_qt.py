"""
Stream Deck (Qt Edition)
========================
Versión ligera orientada a usuarios no técnicos.

Objetivo:
- UI más fluida usando Qt (PySide6) en lugar de Tkinter.
- Flujo simple: seleccionar botón -> elegir acción -> valor -> guardar/probar.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import webbrowser
from dataclasses import dataclass, asdict
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

CONFIG_FILE = "streamdeck_qt_profile.json"
GRID_COLS = 4
GRID_ROWS = 4
TOTAL_BTNS = GRID_COLS * GRID_ROWS

ACTION_ITEMS = [
    ("Abrir programa", "program"),
    ("Abrir sitio web", "url"),
    ("Abrir archivo", "file"),
    ("Pegar texto", "text"),
]


@dataclass
class ButtonConfig:
    name: str = ""
    action_type: str = ""
    action_value: str = ""


class StreamDeckQt(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Stream Deck · Qt")
        self.resize(1180, 760)

        self._buttons_data: List[ButtonConfig] = self._load_data()
        self._selected_idx = 0
        self._grid_buttons: List[QPushButton] = []

        self._build_ui()
        self._paint_grid()
        self._load_editor(0)

    # ------------------------- UI -------------------------

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(10, 10, 10, 10)

        toolbar = QToolBar("Acciones")
        self.addToolBar(toolbar)

        save_action = QAction("Guardar", self)
        save_action.triggered.connect(self._save_data)
        toolbar.addAction(save_action)

        test_action = QAction("Probar", self)
        test_action.triggered.connect(self._test_current)
        toolbar.addAction(test_action)

        splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(splitter, 1)

        # Panel izquierdo: grid
        left = QFrame()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)

        left_title = QLabel("Botones")
        left_title.setStyleSheet("font-weight: 700; font-size: 16px;")
        left_layout.addWidget(left_title)

        grid_wrap = QWidget()
        grid = QGridLayout(grid_wrap)
        grid.setSpacing(8)
        for i in range(TOTAL_BTNS):
            btn = QPushButton(f"Botón {i + 1}")
            btn.setMinimumHeight(74)
            btn.clicked.connect(lambda _, idx=i: self._select_button(idx))
            self._grid_buttons.append(btn)
            grid.addWidget(btn, i // GRID_COLS, i % GRID_COLS)
        left_layout.addWidget(grid_wrap, 1)

        # Panel derecho: editor simple
        right = QFrame()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 12, 12, 12)

        title = QLabel("Editor simple")
        title.setStyleSheet("font-weight: 700; font-size: 16px;")
        right_layout.addWidget(title)

        form = QFormLayout()

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Ej: Abrir correo")
        form.addRow("Nombre", self.name_input)

        self.type_combo = QComboBox()
        for label, code in ACTION_ITEMS:
            self.type_combo.addItem(label, code)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Acción", self.type_combo)

        self.value_input = QLineEdit()
        self.value_input.setPlaceholderText("Completa el valor según la acción")
        form.addRow("Valor", self.value_input)

        right_layout.addLayout(form)

        helper_row = QHBoxLayout()
        pick_file_btn = QPushButton("📂 Elegir archivo")
        pick_file_btn.clicked.connect(self._pick_file)
        helper_row.addWidget(pick_file_btn)
        helper_row.addStretch(1)
        right_layout.addLayout(helper_row)

        right_layout.addWidget(QLabel("Vista rápida"))
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(180)
        right_layout.addWidget(self.preview)

        controls = QHBoxLayout()
        save_btn = QPushButton("Guardar botón")
        save_btn.clicked.connect(self._save_current)
        controls.addWidget(save_btn)

        run_btn = QPushButton("Probar botón")
        run_btn.clicked.connect(self._test_current)
        controls.addWidget(run_btn)

        controls.addStretch(1)
        right_layout.addLayout(controls)

        right_layout.addStretch(1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([640, 540])

    # ------------------------- Data -------------------------

    def _load_data(self) -> List[ButtonConfig]:
        if not os.path.exists(CONFIG_FILE):
            return [ButtonConfig(name=f"Botón {i + 1}") for i in range(TOTAL_BTNS)]

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            items = [ButtonConfig(**b) for b in raw.get("buttons", [])]
            if len(items) < TOTAL_BTNS:
                items.extend(ButtonConfig(name=f"Botón {i + 1}") for i in range(len(items), TOTAL_BTNS))
            return items[:TOTAL_BTNS]
        except Exception:
            return [ButtonConfig(name=f"Botón {i + 1}") for i in range(TOTAL_BTNS)]

    def _save_data(self) -> None:
        data = {"buttons": [asdict(b) for b in self._buttons_data]}
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self.statusBar().showMessage("Perfil guardado", 2500)

    # ------------------------- Interaction -------------------------

    def _select_button(self, idx: int) -> None:
        self._save_current(silent=True)
        self._selected_idx = idx
        self._load_editor(idx)

    def _load_editor(self, idx: int) -> None:
        cfg = self._buttons_data[idx]
        self.name_input.setText(cfg.name or f"Botón {idx + 1}")

        combo_idx = next(
            (i for i, (_, code) in enumerate(ACTION_ITEMS) if code == cfg.action_type),
            0,
        )
        self.type_combo.setCurrentIndex(combo_idx)
        self.value_input.setText(cfg.action_value or "")
        self._refresh_preview()
        self._paint_grid()

    def _save_current(self, silent: bool = False) -> None:
        idx = self._selected_idx
        action_type = self.type_combo.currentData()
        cfg = ButtonConfig(
            name=self.name_input.text().strip() or f"Botón {idx + 1}",
            action_type=action_type,
            action_value=self.value_input.text().strip(),
        )
        self._buttons_data[idx] = cfg
        self._refresh_preview()
        self._paint_grid()
        if not silent:
            self._save_data()

    def _paint_grid(self) -> None:
        for i, btn in enumerate(self._grid_buttons):
            cfg = self._buttons_data[i]
            label = cfg.name or f"Botón {i + 1}"
            action_text = next((l for l, code in ACTION_ITEMS if code == cfg.action_type), "Sin acción")
            btn.setText(f"{label}\n{action_text}")
            btn.setStyleSheet(
                "QPushButton {padding: 8px; text-align: left; border-radius: 10px; border: 1px solid #30343f;}"
                if i != self._selected_idx
                else "QPushButton {padding: 8px; text-align: left; border-radius: 10px; border: 2px solid #5865f2;}"
            )

    def _refresh_preview(self) -> None:
        action_label = self.type_combo.currentText()
        self.preview.setPlainText(
            f"Botón: {self.name_input.text() or f'Botón {self._selected_idx + 1}'}\n"
            f"Acción: {action_label}\n"
            f"Valor: {self.value_input.text()}"
        )

    def _on_type_changed(self) -> None:
        action = self.type_combo.currentData()
        placeholders = {
            "program": "Ej: calc o notepad.exe",
            "url": "Ej: https://google.com",
            "file": "Ruta de archivo...",
            "text": "Texto a copiar al portapapeles",
        }
        self.value_input.setPlaceholderText(placeholders.get(action, "Ingresá valor"))
        self._refresh_preview()

    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Elegir archivo")
        if path:
            self.value_input.setText(path)
            self._refresh_preview()

    # ------------------------- Action execution -------------------------

    def _test_current(self) -> None:
        self._save_current(silent=True)
        cfg = self._buttons_data[self._selected_idx]

        if not cfg.action_type or not cfg.action_value:
            QMessageBox.information(self, "Falta configuración", "Completá acción y valor antes de probar.")
            return

        try:
            if cfg.action_type == "program":
                subprocess.Popen(cfg.action_value, shell=True)
            elif cfg.action_type == "url":
                webbrowser.open(cfg.action_value)
            elif cfg.action_type == "file":
                if sys.platform.startswith("win"):
                    os.startfile(cfg.action_value)  # type: ignore[attr-defined]
                else:
                    subprocess.Popen(["xdg-open", cfg.action_value])
            elif cfg.action_type == "text":
                QApplication.clipboard().setText(cfg.action_value)
            QMessageBox.information(self, "OK", "Acción ejecutada correctamente.")
        except Exception as exc:
            QMessageBox.warning(self, "Error", f"No se pudo ejecutar la acción:\n{exc}")


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = StreamDeckQt()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
