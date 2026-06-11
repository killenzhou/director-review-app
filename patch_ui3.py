path = r'y:\killen\协同审阅平台\director_review_app-原文件\director_review_app\ui_components.py'

replacement = '''
class DepartmentSelectionDialog(QDialog):
    def __init__(self, available_departments, current_selection, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置部门")
        self.setMinimumWidth(300)
        self.available_departments = available_departments
        if isinstance(current_selection, str):
            self.current_selection = [s.strip() for s in current_selection.replace("，", ",").split(",") if s.strip()]
        else:
            self.current_selection = current_selection or []
        
        self.checkboxes = []
        
        layout = QVBoxLayout(self)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        for dept in self.available_departments:
            cb = QCheckBox(dept)
            if dept in self.current_selection:
                cb.setChecked(True)
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
        selected = [cb.text() for cb in self.checkboxes if cb.isChecked()]
        return ", ".join(selected)
'''

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

import re
content = re.sub(r'class MultiSelectComboBox\(QComboBox\):.*', '', content, flags=re.DOTALL)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content + replacement)
