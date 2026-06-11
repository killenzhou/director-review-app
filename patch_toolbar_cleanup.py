path = r'y:\killen\协同审阅平台\director_review_app-原文件\director_review_app\main_app.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Remove connection
content = content.replace('        self.whisper_model_selector.currentTextChanged.connect(self.on_model_changed)', '')

# 2. Add cleanup_temp_folders
cleanup_method = '''
    def cleanup_temp_folders(self):
        import os
        import shutil
        from PySide6.QtWidgets import QMessageBox
        temp_dir_base = getattr(self.project_manager, 'temp_dir_base', os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp"))
        if not os.path.exists(temp_dir_base):
            QMessageBox.information(self, "清理", "没有发现任何临时文件夹。")
            return
            
        current_temp = getattr(self.project_manager, 'current_temp_dir', None)
        to_delete = []
        total_size = 0
        
        for item in os.listdir(temp_dir_base):
            item_path = os.path.join(temp_dir_base, item)
            if os.path.isdir(item_path):
                # Don't delete if it's currently active
                if current_temp and os.path.abspath(item_path) == os.path.abspath(current_temp):
                    continue
                to_delete.append(item_path)
                for dirpath, _, filenames in os.walk(item_path):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        if not os.path.islink(fp):
                            total_size += os.path.getsize(fp)
                            
        if not to_delete:
            QMessageBox.information(self, "清理", "目前只有当前正在使用的临时工程，无需清理。")
            return
            
        size_mb = total_size / (1024 * 1024)
        reply = QMessageBox.question(self, "确认清理", f"找到了 {len(to_delete)} 个历史无名临时工程（Temp 文件夹）。\\n预计可释放 {size_mb:.2f} MB 空间。\\n\\n是否确定永久删除它们？（此操作不可逆！）")
        if reply == QMessageBox.Yes:
            deleted_count = 0
            for d in to_delete:
                try:
                    shutil.rmtree(d)
                    deleted_count += 1
                except Exception as e:
                    print(f"Failed to delete {d}: {e}")
            QMessageBox.information(self, "清理完成", f"成功清理了 {deleted_count} 个历史临时工程。")

'''

import re
# Insert the method before show_table_context_menu
content = re.sub(r'    def show_table_context_menu', cleanup_method.lstrip() + '    def show_table_context_menu', content)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
