# SPDX-License-Identifier: LGPL-2.1-or-later
"""Small preference dialog (also backed by ParamGet / preference page)."""

from __future__ import annotations

from PySide.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

from neoribbon import prefs


class PreferencesDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("NeoRibbon")
        self.setModal(True)
        self.resize(440, 300)

        self.enabled = QCheckBox("Enable ribbon")
        self.hide_menubar = QCheckBox("Hide menu bar while ribbon is enabled")
        self.hide_menubar.setToolTip(
            "Escape hatch if the menu bar disappears: Ctrl+Shift+M shows the "
            "menu bar; Ctrl+Shift+R restores classic toolbars. "
            "Ctrl+Shift+N toggles NeoRibbon."
        )
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
        form.addRow(self.hide_menubar)
        form.addRow(self.promote_large)
        form.addRow(self.show_labels)
        form.addRow("Button size", self.button_size)
        form.addRow("Visible commands / section", self.visible_count)
        form.addRow("Ignored toolbars", self.ignored)

        hint = QLabel(
            "Each section shows your most-used commands; extras are under More. "
            "Hide sections with × on the section title, or Sections ▾. "
            "If the menu bar is hidden: Ctrl+Shift+M shows it; "
            "Ctrl+Shift+R restores classic toolbars."
        )
        hint.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(hint)
        root.addWidget(buttons)

        self._load()

    def _load(self) -> None:
        self.enabled.setChecked(prefs.is_enabled())
        self.hide_menubar.setChecked(prefs.hide_menubar())
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
        hide = self.hide_menubar.isChecked()
        if hide and not prefs.hide_menubar():
            answer = QMessageBox.question(
                self,
                "Hide FreeCAD menu bar?",
                "This hides Edit/Tools/View until NeoRibbon restores them.\n\n"
                "Remember: Ctrl+Shift+M shows the menu bar; Ctrl+Shift+R "
                "restores classic toolbars — both work with menus gone.\n\n"
                "Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.hide_menubar.setChecked(False)
                hide = False
        prefs.set_enabled(self.enabled.isChecked())
        prefs.set_hide_menubar(hide)
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
