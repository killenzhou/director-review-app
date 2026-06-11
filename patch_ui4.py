path = r'y:\killen\协同审阅平台\director_review_app-原文件\director_review_app\ui_components.py'

replacement = '''
class DepartmentSelectionDialog(QDialog):
    def __init__(self, available_departments, current_selection, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置部门")
        self.setMinimumWidth(350)
        self.available_departments = available_departments
        if isinstance(current_selection, str):
            self.current_selection = [s.strip() for s in current_selection.replace("，", ",").split(",") if s.strip()]
        else:
            self.current_selection = current_selection or []
        
        self.checkboxes = []
        
        layout = QVBoxLayout(self)
        
        from PySide6.QtWidgets import QLineEdit, QLabel
        layout.addWidget(QLabel("当前选中 (可手动编辑):"))
        self.text_input = QLineEdit()
        self.text_input.setText(", ".join(self.current_selection))
        layout.addWidget(self.text_input)
        
        layout.addWidget(QLabel("快速勾选:"))
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        self._updating = False
        
        def on_checkbox_toggled():
            if self._updating: return
            self._updating = True
            selected = [cb.text() for cb in self.checkboxes if cb.isChecked()]
            
            manual_text = self.text_input.text()
            manual_items = [s.strip() for s in manual_text.replace("，", ",").split(",") if s.strip()]
            custom_items = [item for item in manual_items if item not in self.available_departments]
            
            all_selected = selected + custom_items
            self.text_input.setText(", ".join(all_selected))
            self._updating = False
            
        def on_text_changed():
            if self._updating: return
            self._updating = True
            manual_text = self.text_input.text()
            manual_items = [s.strip() for s in manual_text.replace("，", ",").split(",") if s.strip()]
            for cb in self.checkboxes:
                cb.setChecked(cb.text() in manual_items)
            self._updating = False

        self.text_input.textEdited.connect(on_text_changed)
        
        for dept in self.available_departments:
            cb = QCheckBox(dept)
            if dept in self.current_selection:
                cb.setChecked(True)
            cb.toggled.connect(on_checkbox_toggled)
            self.checkboxes.append(cb)
            scroll_layout.addWidget(cb)
            
        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_widget)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        layout.addWidget(scroll_area)
        layout.addWidget(button_box)
        
    def get_selected_departments(self):
        return self.text_input.text().strip()
'''

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

import re
content = re.sub(r'class DepartmentSelectionDialog\(QDialog\):.*', '', content, flags=re.DOTALL)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content + replacement)
