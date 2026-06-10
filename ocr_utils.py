# -*- coding: utf-8 -*-
import re
import sys
import os
import subprocess
import tempfile

_tesseract_initialized = False
_tesseract_error_message = "Tesseract OCR 未能成功初始化。请检查安装或打包配置。"
_tesseract_cmd_path = None
_tesseract_tessdata_prefix = None

def _test_tesseract_config(cmd_path, tessdata_prefix):
    print(f"DEBUG: Testing Tesseract config: cmd='{cmd_path}', tessdata='{tessdata_prefix}'")
    try:
        command = [cmd_path, '--version']
        if tessdata_prefix:
            command.insert(1, '--tessdata-dir')
            command.insert(2, tessdata_prefix)

        # Set the working directory to the executable's directory to find DLLs
        cwd = os.path.dirname(cmd_path) if os.path.isabs(cmd_path) else None
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore',
                              creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                              cwd=cwd)
        
        print(f"DEBUG: Tesseract test exited with code {proc.returncode}")
        print(f"DEBUG: Tesseract test stdout: {proc.stdout.strip()}")
        print(f"DEBUG: Tesseract test stderr: {proc.stderr.strip()}")

        if proc.returncode == 0 and 'tesseract' in proc.stdout:
            print("INFO: Tesseract configuration test successful.")
            return True
        else:
            print(f"WARNING: Tesseract version check failed. Stderr: {proc.stderr.strip()}")
            return False
            
    except Exception as e:
        print(f"ERROR: Tesseract configuration test threw an exception: {e}")
        return False

def _initialize_tesseract():
    global _tesseract_initialized, _tesseract_error_message, _tesseract_cmd_path, _tesseract_tessdata_prefix
    print("INFO: Initializing Tesseract...")

    if _tesseract_initialized:
        print("INFO: Tesseract already initialized.")
        return True

    # Strategy 1: Portable Tesseract next to the executable.
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.abspath(".")
    portable_dir = os.path.join(exe_dir, 'Tesseract-OCR')
    cmd_path = os.path.join(portable_dir, 'tesseract.exe')
    tessdata_prefix = os.path.join(portable_dir, 'tessdata')
    print(f"DEBUG: Portable paths: cmd='{cmd_path}', tessdata='{tessdata_prefix}'")
    if os.path.exists(cmd_path) and os.path.isdir(tessdata_prefix):
        print("INFO: Found portable Tesseract-OCR folder.")
        if _test_tesseract_config(cmd_path, tessdata_prefix):
            _tesseract_cmd_path = cmd_path
            _tesseract_tessdata_prefix = tessdata_prefix
            _tesseract_initialized = True
            print("INFO: Portable Tesseract initialized successfully.")
            return True

    # Strategy 2: Bundled Tesseract inside PyInstaller _internal/_MEIPASS.
    if hasattr(sys, '_MEIPASS'):
        print("INFO: Running in bundled mode, checking for local Tesseract-OCR.")
        bundled_dir = os.path.join(sys._MEIPASS, 'Tesseract-OCR')
        cmd_path = os.path.join(bundled_dir, 'tesseract.exe')
        tessdata_prefix = os.path.join(bundled_dir, 'tessdata')
        print(f"DEBUG: Bundled paths: cmd='{cmd_path}', tessdata='{tessdata_prefix}'")
        
        if os.path.exists(cmd_path) and os.path.isdir(tessdata_prefix):
            print("INFO: Found bundled tesseract.exe and tessdata directory.")
            if _test_tesseract_config(cmd_path, tessdata_prefix):
                _tesseract_cmd_path = cmd_path
                _tesseract_tessdata_prefix = tessdata_prefix
                _tesseract_initialized = True
                print("INFO: Bundled Tesseract initialized successfully.")
                return True
            else:
                print("ERROR: Bundled Tesseract test failed.")
        else:
            print(f"ERROR: Bundled Tesseract files not found. cmd_exists={os.path.exists(cmd_path)}, tessdata_exists={os.path.isdir(tessdata_prefix)}")

    # Strategy 3: Development mode (local folder)
    else:
        print("INFO: Not in bundled mode, checking for local Tesseract-OCR folder for development.")
        dev_dir = os.path.abspath('Tesseract-OCR')
        cmd_path = os.path.join(dev_dir, 'tesseract.exe')
        tessdata_prefix = os.path.join(dev_dir, 'tessdata')
        print(f"DEBUG: Development paths: cmd='{cmd_path}', tessdata='{tessdata_prefix}'")

        if os.path.exists(cmd_path) and os.path.isdir(tessdata_prefix):
            print("INFO: Found local Tesseract-OCR folder for development.")
            if _test_tesseract_config(cmd_path, tessdata_prefix):
                _tesseract_cmd_path = cmd_path
                _tesseract_tessdata_prefix = tessdata_prefix
                _tesseract_initialized = True
                print("INFO: Local Tesseract initialized successfully for development.")
                return True
            else:
                print("ERROR: Local Tesseract test failed.")

    # Strategy 4: System PATH Tesseract (Fallback)
    print("INFO: Checking for Tesseract in system PATH.")
    if _test_tesseract_config('tesseract', None):
        _tesseract_cmd_path = 'tesseract'
        _tesseract_tessdata_prefix = None
        _tesseract_initialized = True
        print("INFO: System PATH Tesseract initialized successfully.")
        return True

    _tesseract_error_message = "Tesseract OCR 未能成功初始化。请确保已安装并将其添加到系统 PATH，或确认打包配置正确。"
    print(f"ERROR: {_tesseract_error_message}")
    return False

_initialize_tesseract()

def image_to_string(image, lang='chi_sim'):
    if not _tesseract_initialized:
        print("ERROR: Tesseract not initialized. Returning error message.")
        return _tesseract_error_message
    
    try:
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            input_filename = temp_file.name
            image.save(input_filename)

        command = [_tesseract_cmd_path, input_filename, 'stdout', '--psm', '3']
        if _tesseract_tessdata_prefix:
            command.extend(['--tessdata-dir', _tesseract_tessdata_prefix])
        command.extend(['-l', lang])
        
        print(f"DEBUG: Running OCR command: {' '.join(command)}")
        # Set the working directory to the executable's directory to find DLLs
        cwd = os.path.dirname(_tesseract_cmd_path) if os.path.isabs(_tesseract_cmd_path) else None
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore',
                              creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                              cwd=cwd)
        os.remove(input_filename)
        
        output_text = proc.stdout.strip()
        error_text = proc.stderr.strip()
        
        print(f"DEBUG: OCR process exited with code {proc.returncode}")
        if output_text: print(f"DEBUG: OCR stdout: {output_text[:200]}")
        if error_text: print(f"DEBUG: OCR stderr: {error_text}")
            
        if proc.returncode != 0:
            print(f"WARNING: Tesseract exited with code {proc.returncode}. Stderr: {error_text}")
            return output_text or f"OCR执行错误: {error_text}"
            
        return output_text
        
    except Exception as e:
        print(f"ERROR: image_to_string threw an exception: {e}")
        return f"OCR失败: {e}"

def find_timestamp(raw_text):
    if not raw_text: return "未识别"
    # Prioritize longer, more specific formats
    if match := re.search(r'(\d{1,2}:\d{2}:\d{2}:\d{2,3})', raw_text): return match.group(1)
    if match := re.search(r'(\d{1,2}:\d{2}:\d{2})', raw_text): return match.group(1)
    if match := re.search(r'(\d{1,2}:\d{2})', raw_text): return match.group(1)
    return "未识别"

def _extract_production_shot_number(raw_text):
    # EP01_SC001_0010, EP1_SC1_1
    if match := re.search(r'([Ee][Pp]\d{1,3}[\W_]*[Ss][Cc]\d{1,4}[\W_]*\d{1,4})', raw_text, re.IGNORECASE):
        return re.sub(r'[\W_]+', '_', match.group(1)).upper()
    return None

def _format_director_shot_number(raw_text):
    # Flexible matching for "ep 1 sc 2 30"
    if match := re.search(r"[Ee][Pp]?\D*(\d+)\D*[Ss][Cc]?\D*(\d+)\D*(\d+)", raw_text, re.IGNORECASE):
        ep, sc, shot = match.groups()
        return f"EP{ep.zfill(2)}_SC{sc.zfill(3)}_{shot.zfill(4)}"
    # Match three numbers in a row as a fallback
    if len(numbers := re.findall(r'\d+', raw_text)) >= 3:
        return f"EP{numbers[0].zfill(2)}_SC{numbers[1].zfill(3)}_{numbers[2].zfill(4)}"
    return None

def extract_shot_number(raw_text):
    if not raw_text: return "未识别"
    cleaned_text = raw_text.replace('O', '0').replace('o', '0').replace('I', '1').replace('l', '1')
    if shot := _extract_production_shot_number(cleaned_text): return shot
    if shot := _format_director_shot_number(cleaned_text): return shot
    return "未识别"

def ocr_timestamp_from_image(image):
    return find_timestamp(image_to_string(image, lang='chi_sim'))

def ocr_shot_number_from_image(image):
    return extract_shot_number(image_to_string(image, lang='chi_sim'))
