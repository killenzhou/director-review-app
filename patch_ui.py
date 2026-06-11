import os

path = r'y:\killen\协同审阅平台\director_review_app-原文件\director_review_app\ui_components.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add MultiSelectComboBox to imports if needed (we will just define it at the bottom or top)
# Actually, let's insert it after FlowLayout definition or imports.

target = '''class FlowLayout(QLayout):'''

replacement = '''class MultiSelectComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        from PySide6.QtGui import QStandardItemModel, QStandardItem
        self._model = QStandardItemModel()
        self.setModel(self._model)
        self._model.itemChanged.connect(self.update_text_from_items)
        self.lineEdit().textEdited.connect(self.update_items_from_text)
        self.view().viewport().installEventFilter(self)
        self._updating = False

    def addItems(self, items):
        from PySide6.QtGui import QStandardItem
        from PySide6.QtCore import Qt
        for text in items:
            item = QStandardItem(text)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setData(Qt.Unchecked, Qt.CheckStateRole)
            self._model.appendRow(item)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent, Qt
        if obj == self.view().viewport() and event.type() == QEvent.MouseButtonRelease:
            index = self.view().indexAt(event.pos())
            if index.isValid():
                item = self._model.itemFromIndex(index)
                if item.checkState() == Qt.Checked:
                    item.setCheckState(Qt.Unchecked)
                else:
                    item.setCheckState(Qt.Checked)
                return True
        return super().eventFilter(obj, event)

    def update_text_from_items(self):
        if self._updating: return
        self._updating = True
        from PySide6.QtCore import Qt
        checked_items = []
        for i in range(self._model.rowCount()):
            item = self._model.item(i)
            if item.checkState() == Qt.Checked:
                checked_items.append(item.text())
        text = ", ".join(checked_items)
        self.lineEdit().setText(text)
        self.currentTextChanged.emit(text)
        self._updating = False

    def update_items_from_text(self, text):
        if self._updating: return
        self._updating = True
        from PySide6.QtCore import Qt
        selected = [s.strip() for s in text.replace("，", ",").split(",") if s.strip()]
        for i in range(self._model.rowCount()):
            item = self._model.item(i)
            if item.text() in selected:
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
        self._updating = False

    def setCurrentText(self, text):
        super().setCurrentText(text)
        self.update_items_from_text(text)

class FlowLayout(QLayout):'''

content = content.replace(target, replacement)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("ui_components patched")
