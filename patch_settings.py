import sys

path = r'y:\killen\协同审阅平台\director_review_app-原文件\director_review_app\settings_dialog.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

target1 = '''        self.departments_input = QLineEdit()
        self.departments_input.setReadOnly(True)
        self.departments_input.setToolTip("部门列表已固定在程序设置中")'''
replacement1 = '''        self.departments_input = QLineEdit()
        self.departments_input.setToolTip("输入全局部门列表（使用逗号分隔）。例如：动画, 灯光, 特效")'''

target2 = '''        departments = DEFAULT_DEPARTMENTS.copy(); self.departments_input.setText(", ".join(departments))'''
replacement2 = '''        departments = self.settings.get("departments", DEFAULT_DEPARTMENTS.copy())
        self.departments_input.setText(", ".join(departments))'''

target3 = '''        departments = DEFAULT_DEPARTMENTS.copy()'''
replacement3 = '''        raw_depts = self.departments_input.text()
        departments = [d.strip() for d in raw_depts.replace("，", ",").split(",") if d.strip()]
        if not departments:
            departments = DEFAULT_DEPARTMENTS.copy()'''

content = content.replace(target1, replacement1)
content = content.replace(target2, replacement2)
# Since target3 appears multiple times, we only want to replace the one in get_settings
# target3 is exactly "        departments = DEFAULT_DEPARTMENTS.copy()"
get_settings_block = '''    def get_settings(self):
        departments = DEFAULT_DEPARTMENTS.copy()'''
get_settings_replacement = '''    def get_settings(self):
        raw_depts = self.departments_input.text()
        departments = [d.strip() for d in raw_depts.replace("，", ",").split(",") if d.strip()]
        if not departments:
            departments = DEFAULT_DEPARTMENTS.copy()'''
content = content.replace(get_settings_block, get_settings_replacement)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Settings dialog patched")
