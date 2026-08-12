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
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from neoribbon import prefs


def _version_label_text() -> str:
    version = prefs.addon_version()
    return f"NeoRibbon {version}" if version else "NeoRibbon"


def _ui_path() -> str:
    return os.path.join(prefs.addon_root(), "Resources", "ui", "preferences.ui")


class PreferencePage:
    """Edit → Preferences → NeoRibbon. Apply/OK write params and refresh live."""

    def __init__(self, parent=None) -> None:  # noqa: ARG002
        import FreeCADGui as Gui

        self.form = Gui.PySideUic.loadUi(_ui_path())
        self._set_version_label()

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
        from neoribbon import bootstrap

        bootstrap.apply_prefs()


class PreferencesDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("NeoRibbon")
        self.setModal(True)
        self.resize(440, 280)

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

        hint = QLabel(
            "Each section shows your most-used commands; extras are under More. "
            "Hide sections with × on the section title, Sections ▾, or "
            "the checkboxes in Reorder sections…. "
            "Reorder groups from Sections ▾ → Reorder sections…. "
            "Ctrl+Shift+R restores classic toolbars if needed."
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


def open_preferences_dialog() -> None:
    from FreeCADGui import getMainWindow

    dialog = PreferencesDialog(getMainWindow())
    if dialog.exec() == QDialog.DialogCode.Accepted:
        dialog.apply()
        from neoribbon import bootstrap

        bootstrap.apply_prefs()
