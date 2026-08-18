# SPDX-License-Identifier: LGPL-2.1-or-later
"""Small preference dialog (also backed by ParamGet / preference page)."""

from __future__ import annotations

import os

from PySide.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from freecad.NeoRibbon import prefs
from freecad.NeoRibbon.shortcut_edit import (
    create_reset_shortcut_button,
    create_shortcut_recorder,
    recorded_shortcut_text,
    set_recorded_shortcut,
)


def _version_label_text() -> str:
    version = prefs.addon_version()
    return f"NeoRibbon {version}" if version else "NeoRibbon"


def _ui_path() -> str:
    return os.path.join(prefs.addon_root(), "Resources", "ui", "preferences.ui")


def _persist_toggle_shortcut(seq: str) -> None:
    from freecad.NeoRibbon import bootstrap

    bootstrap.try_set_shortcuts({"toggle": seq}, interactive=False, persist=True)


def _install_shortcut_editors(parent, form_layout, on_reset) -> dict[str, object]:
    """Add recorder + Reset rows to a QFormLayout. Returns kind → edit."""
    edits: dict[str, object] = {}
    for kind, label in prefs.SHORTCUT_ROWS:
        edit = create_shortcut_recorder(
            parent, default=prefs.shortcut_default(kind)
        )
        edit._on_shortcut_accepted = _persist_toggle_shortcut  # noqa: SLF001
        reset = create_reset_shortcut_button(
            parent, default=prefs.shortcut_default(kind)
        )
        reset.clicked.connect(lambda *args, k=kind: on_reset(k))
        row = QWidget(parent)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit, 1)
        layout.addWidget(reset)
        form_layout.addRow(label, row)
        edits[kind] = edit
    return edits


def _load_shortcut_fields(edits: dict[str, object]) -> None:
    for kind, edit in edits.items():
        default = prefs.shortcut_default(kind)
        set_recorded_shortcut(edit, prefs.shortcut(kind), default=default)


def _reset_shortcut_field(edits: dict[str, object], kind: str) -> None:
    default = prefs.shortcut_default(kind)
    set_recorded_shortcut(
        edits.get(kind), default, default=default, validate=True
    )


def _save_shortcut_fields(edits: dict[str, object]) -> None:
    from freecad.NeoRibbon import bootstrap

    desired = {
        kind: recorded_shortcut_text(edit) or prefs.shortcut_default(kind)
        for kind, edit in edits.items()
    }
    if not bootstrap.try_set_shortcuts(desired, interactive=True):
        _load_shortcut_fields(edits)


def _restore_classic_clicked(enable_widget) -> None:
    from freecad.NeoRibbon import bootstrap

    bootstrap.restore_toolbars()
    if enable_widget is not None:
        try:
            enable_widget.setChecked(False)
        except Exception:
            pass


def _restore_button_tooltip() -> str:
    return (
        "Re-dock classic toolbars (including bars missing from "
        "View → Toolbars) and disable the ribbon. "
        "Takes effect immediately (does not wait for Apply)."
    )


class PreferencePage:
    """Edit → Preferences → NeoRibbon. Apply/OK write params and refresh live."""

    def __init__(self, parent=None) -> None:  # noqa: ARG002
        import FreeCADGui as Gui

        self.form = Gui.PySideUic.loadUi(_ui_path())
        self._shortcut_edits: dict[str, object] = {}
        self._wire_shortcut_editors()
        self._wire_restore_button()
        self._set_version_label()

    def _wire_shortcut_editors(self) -> None:
        group = getattr(self.form, "groupShortcuts", None)
        form_layout = group.layout() if group is not None else None
        if form_layout is None:
            form_layout = getattr(self.form, "formShortcuts", None)
        if form_layout is None:
            import FreeCAD as App

            App.Console.PrintWarning(
                "NeoRibbon: preference shortcut layout missing; "
                "keyboard shortcuts cannot be edited on this page\n"
            )
            return
        self._shortcut_edits = _install_shortcut_editors(
            self.form,
            form_layout,
            lambda kind: _reset_shortcut_field(self._shortcut_edits, kind),
        )

    def _wire_restore_button(self) -> None:
        btn = getattr(self.form, "buttonRestoreClassic", None)
        if btn is None:
            return
        btn.setToolTip(_restore_button_tooltip())
        btn.clicked.connect(
            lambda *args: _restore_classic_clicked(
                getattr(self.form, "checkEnabled", None)
            )
        )

    def _set_version_label(self) -> None:
        label = getattr(self.form, "labelVersion", None)
        if label is not None:
            label.setText(_version_label_text())

    def loadSettings(self) -> None:  # noqa: N802 — FreeCAD preference page API
        form = self.form
        form.checkEnabled.setChecked(prefs.is_enabled())
        form.checkPromoteLarge.setChecked(prefs.promote_large())
        form.checkShowButtonLabels.setChecked(prefs.show_button_labels())
        form.comboButtonSize.setCurrentIndex(prefs.button_size_index())
        form.spinVisiblePerSection.setValue(prefs.visible_per_section())
        form.lineIgnoredToolbars.setText(prefs.ignored_toolbars_text())
        _load_shortcut_fields(self._shortcut_edits)
        self._set_version_label()

    def saveSettings(self) -> None:  # noqa: N802 — FreeCAD preference page API
        form = self.form
        prefs.set_enabled(form.checkEnabled.isChecked())
        prefs.set_promote_large(form.checkPromoteLarge.isChecked())
        prefs.set_show_button_labels(form.checkShowButtonLabels.isChecked())
        idx = form.comboButtonSize.currentIndex()
        if 0 <= idx < len(prefs.BUTTON_SIZES):
            prefs.set_button_size(prefs.BUTTON_SIZES[idx])
        prefs.set_visible_per_section(form.spinVisiblePerSection.value())
        prefs.set_ignored_toolbars_text(form.lineIgnoredToolbars.text())
        _save_shortcut_fields(self._shortcut_edits)
        from freecad.NeoRibbon import bootstrap

        bootstrap.apply_prefs()


class PreferencesDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("NeoRibbon")
        self.setModal(True)
        self.resize(480, 420)

        self.enabled = QCheckBox("Enable ribbon")
        self.promote_large = QCheckBox("Large icon for first command in each section")
        self.show_labels = QCheckBox("Text labels on ribbon buttons")
        self.show_labels.setToolTip(
            "When off, the focus strip shows icons only. "
            "Section dropdown lists always keep text labels."
        )
        self.button_size = QComboBox()
        for size in prefs.BUTTON_SIZES:
            self.button_size.addItem(size.capitalize(), size)
        self.visible_count = QSpinBox()
        self.visible_count.setRange(1, 24)
        self.visible_count.setToolTip(
            "Most-used commands shown per section; the rest go under More"
        )
        self.ignored = QLineEdit()
        self.ignored.setPlaceholderText("Toolbar names separated by ;")

        form = QFormLayout()
        form.addRow(self.enabled)
        form.addRow(self.promote_large)
        form.addRow(self.show_labels)
        form.addRow("Button size", self.button_size)
        form.addRow("Visible commands / section", self.visible_count)
        form.addRow("Ignored toolbars", self.ignored)

        shortcut_box = QGroupBox("Keyboard shortcuts")
        shortcut_form = QFormLayout(shortcut_box)
        self._shortcut_edits = _install_shortcut_editors(
            self,
            shortcut_form,
            lambda kind: _reset_shortcut_field(self._shortcut_edits, kind),
        )
        shortcut_hint = QLabel(
            "Click the field, then press keys. Reset restores the default. "
            "A shortcut already used elsewhere is rejected immediately. "
            "A valid chord is saved as soon as you record it."
        )
        shortcut_hint.setWordWrap(True)

        self.restore_classic = QPushButton("Restore classic toolbars")
        self.restore_classic.setToolTip(_restore_button_tooltip())
        self.restore_classic.clicked.connect(
            lambda *args: _restore_classic_clicked(self.enabled)
        )

        hint = QLabel(
            "Each section shows your most-used commands; extras are under More. "
            "Hide sections with × on the section title, Sections ▾, or "
            "the checkboxes in Reorder sections…. "
            "Reorder groups from Sections ▾ → Reorder sections…. "
            "Use Restore classic toolbars only if you need the old toolbar strip back."
        )
        hint.setWordWrap(True)

        version = QLabel(_version_label_text())
        version.setObjectName("labelVersion")
        version.setToolTip("Installed addon version from package.xml")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(shortcut_box)
        root.addWidget(shortcut_hint)
        root.addWidget(self.restore_classic)
        root.addWidget(hint)
        root.addWidget(version)
        root.addWidget(buttons)

        self._load()

    def _load(self) -> None:
        self.enabled.setChecked(prefs.is_enabled())
        self.promote_large.setChecked(prefs.promote_large())
        self.show_labels.setChecked(prefs.show_button_labels())
        size = prefs.button_size()
        index = self.button_size.findData(size)
        if index < 0:
            index = self.button_size.findText(size.capitalize())
        self.button_size.setCurrentIndex(max(0, index))
        self.visible_count.setValue(prefs.visible_per_section())
        self.ignored.setText(prefs.ignored_toolbars_text())
        _load_shortcut_fields(self._shortcut_edits)

    def apply(self) -> None:
        prefs.set_enabled(self.enabled.isChecked())
        prefs.set_promote_large(self.promote_large.isChecked())
        prefs.set_show_button_labels(self.show_labels.isChecked())
        size = self.button_size.currentData()
        if not size:
            size = self.button_size.currentText().lower()
        prefs.set_button_size(str(size))
        prefs.set_visible_per_section(self.visible_count.value())
        prefs.set_ignored_toolbars_text(self.ignored.text())
        _save_shortcut_fields(self._shortcut_edits)


def open_preferences_dialog() -> None:
    from FreeCADGui import getMainWindow

    dialog = PreferencesDialog(getMainWindow())
    if dialog.exec() == QDialog.DialogCode.Accepted:
        dialog.apply()
        from freecad.NeoRibbon import bootstrap

        bootstrap.apply_prefs()
