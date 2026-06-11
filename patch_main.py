path = r'y:\killen\协同审阅平台\director_review_app-原文件\director_review_app\main_app.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

t1 = '        self.review_table.customContextMenuRequested.connect(self.show_table_context_menu)'
r1 = '        self.review_table.customContextMenuRequested.connect(self.show_table_context_menu)\n        self.review_table.cellDoubleClicked.connect(self.on_table_cell_double_clicked)'
content = content.replace(t1, r1)

t2 = '        self.latest_table.customContextMenuRequested.connect(self.show_input_table_context_menu)'
r2 = '        self.latest_table.customContextMenuRequested.connect(self.show_input_table_context_menu)\n        self.latest_table.cellDoubleClicked.connect(self.on_input_table_cell_double_clicked)'
content = content.replace(t2, r2)

new_methods = '''
    def on_table_cell_double_clicked(self, row, col):
        if col == COL_DEPARTMENT:
            self.open_department_dialog(self.review_table, row, col, row)

    def on_input_table_cell_double_clicked(self, row, col):
        if col == COL_DEPARTMENT:
            source_row = self._input_table_source_row(row)
            if source_row >= 0:
                self.open_department_dialog(self.latest_table, row, col, source_row)

    def open_department_dialog(self, table, row, col, source_row):
        available_deps = self.sync_departments_from_settings()
        if "未分类" not in available_deps:
            available_deps = ["未分类"] + available_deps
        entry = self.project_manager.review_entries[source_row]
        current_dep = entry.get("department", "未分类")
        
        from ui_components import DepartmentSelectionDialog
        dialog = DepartmentSelectionDialog(available_deps, current_dep, self)
        
        from PySide6.QtWidgets import QDialog
        if dialog.exec() == QDialog.Accepted:
            new_dep = dialog.get_selected_departments()
            if not new_dep:
                new_dep = "未分类"
            rows = self._selected_department_source_rows(table, col, row, source_row)
            if len(rows) > 1:
                self.project_manager.update_entries(rows, {"department": new_dep}, snapshot_action="Batch Edit Department")
            else:
                self.project_manager.update_entry(source_row, {"department": new_dep}, snapshot_action="Edit Department")
            if self.project_manager.current_project_file:
                self.project_manager.save_project(autosave=True)
            self.apply_filters()

    def show_table_context_menu'''
content = content.replace('    def show_table_context_menu', new_methods)

t3 = '''        elif col == COL_FULL_REVIEW:'''
r3 = '''        elif col == COL_DEPARTMENT:
            context_menu.addAction("批量设置部门...").triggered.connect(lambda: self.open_department_dialog(self.review_table, row, col, row))
        elif col == COL_FULL_REVIEW:'''
content = content.replace(t3, r3, 1)

r4 = '''        elif col == COL_DEPARTMENT:
            context_menu.addAction("批量设置部门...").triggered.connect(lambda: self.open_department_dialog(self.latest_table, input_row, input_col, row))
        elif col == COL_FULL_REVIEW:'''
content = content.replace(t3, r4)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Patched main_app.py')
