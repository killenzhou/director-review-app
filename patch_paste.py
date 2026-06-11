path = r'y:\killen\协同审阅平台\director_review_app-原文件\director_review_app\main_app.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

better_paste = '''
    def _handle_table_paste(self, table):
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtCore import Qt
        text = QGuiApplication.clipboard().text()
        if not text:
            return
        selected_items = table.selectedItems()
        if not selected_items:
            return
        
        # Batch collect updates per column
        updates = {}
        for item in selected_items:
            if not (item.flags() & Qt.ItemIsEditable):
                continue
            row = item.row()
            col = item.column()
            
            source_row = -1
            if table == getattr(self, 'review_table', None):
                source_row = row
            elif table == getattr(self, 'latest_table', None):
                source_row = self._input_table_source_row(row)
                
            if source_row >= 0:
                if source_row not in updates:
                    updates[source_row] = {}
                updates[source_row][col] = text

        if not updates:
            return
            
        field_map = {
            COL_EPISODE: "episode",
            COL_SCENE: "scene",
            COL_TIMESTAMP: "timestamp",
            COL_FULL_REVIEW: "full_review",
            COL_SIMPLIFIED: "simplified_review",
            COL_DEPARTMENT: "department",
        }
        
        table.blockSignals(True)
        self._is_updating_table = True
        
        for source_row, cols in updates.items():
            entry_update = {}
            for col, val in cols.items():
                if col == COL_KEYWORDS:
                    import re
                    keywords = [part.strip() for part in re.split(r"[,，、\n]", val) if part.strip()]
                    entry_update["keywords"] = keywords
                elif col in field_map:
                    value = self._normalize_episode(val) if col == COL_EPISODE else self._normalize_scene(val) if col == COL_SCENE else val
                    entry_update[field_map[col]] = value
            
            if entry_update:
                self.project_manager.update_entry(source_row, entry_update, snapshot_action="Paste Edit")
                
        if self.project_manager.current_project_file:
            self.project_manager.save_project(autosave=True)
            
        self._is_updating_table = False
        table.blockSignals(False)
        self.apply_filters()
'''

import re
content = re.sub(r'    def _handle_table_paste\(self, table\):.*?(?=\n    def |$)', better_paste, content, flags=re.DOTALL)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
