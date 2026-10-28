import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import subprocess
import sys
import ctypes
import threading
import csv
import smtplib
import ftplib
from email.message import EmailMessage
import io
import time
import shutil
import fnmatch
from datetime import datetime, timedelta
import webbrowser
import json
import re
import stat
import base64
import tempfile

# sc_ezBAK_mount
#  wim function

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def format_bytes(size):
    """Converts bytes to a human-readable format (KB, MB, GB, etc.)."""
    try:
        size = float(size)
    except (ValueError, TypeError):
        return "N/A"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

def _encrypt_password(password):
    """Encrypts the password using a simple XOR + Base64 method."""
    if not password:
        return ""
    try:
        # Simple XOR key
        key = 0x5A 
        chars = [ord(c) ^ key for c in password]
        b = bytes(chars)
        encoded = base64.b64encode(b).decode('utf-8')
        return f"ENC:{encoded}"
    except Exception:
        return password

def _decrypt_password(encrypted_password):
    """Decrypts the password if it starts with ENC:."""
    if not encrypted_password:
        return ""
    if not encrypted_password.startswith("ENC:"):
        return encrypted_password
    
    try:
        encoded = encrypted_password[4:]
        b = base64.b64decode(encoded)
        key = 0x5A
        chars = [c ^ key for c in b]
        return "".join(map(chr, chars))
    except Exception:
        return encrypted_password

def get_schedules_config_dir():
    """Returns the directory path for storing schedule configuration files."""
    try:
        appdata = os.environ.get('APPDATA') or os.path.expanduser('~')
        cfg_dir = os.path.join(appdata, 'ezbak_schedules')
        os.makedirs(cfg_dir, exist_ok=True)
        return cfg_dir
    except Exception:
        fallback_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ezbak_schedules')
        os.makedirs(fallback_dir, exist_ok=True)
        return fallback_dir

def log_message(message):
    """Prints a message with a timestamp. Used for headless logging."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Handle multi-line messages by splitting and logging each line
    for line in str(message).splitlines():
        print(f"[{timestamp}] {line}")

def send_email_notification(subject, body, smtp_config):
    """Sends an email notification on failure."""
    if not all(smtp_config.get(k) for k in ['server', 'port', 'sender', 'recipient']):
        log_message("ERROR: Email configuration is incomplete (server, port, sender, recipient are required). Cannot send notification.")
        return

    try:
        msg = EmailMessage()
        msg.set_content(body)
        msg['Subject'] = subject
        msg['From'] = smtp_config['sender']
        msg['To'] = smtp_config['recipient']

        port = int(smtp_config.get('port', 587))
        server = smtp_config['server']
        user = smtp_config.get('user')
        password = _decrypt_password(smtp_config.get('password'))

        log_message(f"Connecting to SMTP server {server}:{port}...")
        
        # Use SMTP_SSL for port 465, otherwise use standard SMTP with STARTTLS
        if port == 465:
            with smtplib.SMTP_SSL(server, port, timeout=20) as s:
                if user and password:
                    s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(server, port, timeout=20) as s:
                s.starttls()
                if user and password:
                    s.login(user, password)
                s.send_message(msg)
        log_message(f"Successfully sent email notification to {smtp_config['recipient']}.")
    except Exception as e:
        log_message(f"FATAL: Failed to send email notification: {e}")
        import traceback
        log_message(traceback.format_exc())


def _cleanup_old_logs(log_folder, retention_days, log_prefix=""):
    """Delete .log files older than `retention_days`.
    Primary criterion: the date embedded in the filename (e.g., Public_backup_YYYY-MM-DD[_HHMMSS][...].log).
    Fallback: file's modified time when date parsing fails.
    Only files starting with `log_prefix` are considered when a prefix is provided.
    """
    try:
        if not os.path.isdir(log_folder) or retention_days <= 0:
            return

        today = datetime.now().date()
        cutoff_date = today - timedelta(days=int(retention_days))

        # Regex: prefix + YYYY-MM-DD + optional _HHMMSS + optional suffixes (e.g., ' - 복사본', ' (2)') + .log
        # Example match: Public_backup_2025-09-01_191439 (2).log
        pattern = None
        if log_prefix:
            pattern = re.compile(rf"^{re.escape(log_prefix)}(\d{{4}}-\d{{2}}-\d{{2}})(?:_[0-9]{{6}})?(?:.*)?\.log$", re.IGNORECASE)
        else:
            # Generic pattern when no prefix provided: *YYYY-MM-DD*.log
            pattern = re.compile(r".*?(\d{4}-\d{2}-\d{2})(?:_[0-9]{6})?(?:.*)?\.log$", re.IGNORECASE)

        deleted = 0
        scanned = 0
        for filename in os.listdir(log_folder):
            if not filename.lower().endswith(".log"):
                continue
            if log_prefix and not filename.lower().startswith(log_prefix.lower()):
                # Only consider logs for this task/prefix when a prefix is set
                continue

            scanned += 1
            filepath = os.path.join(log_folder, filename)

            # Determine the file date
            file_date = None
            m = pattern.match(filename)
            if m:
                try:
                    file_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
                except Exception:
                    file_date = None

            if file_date is None:
                try:
                    file_date = datetime.fromtimestamp(os.path.getmtime(filepath)).date()
                except Exception:
                    # If we cannot determine date, skip the file rather than risking deletion
                    continue

            if file_date < cutoff_date:
                try:
                    os.remove(filepath)
                    log_message(f"  - Deleting old log: {filename} (date={file_date}, cutoff={cutoff_date})")
                    deleted += 1
                except Exception as e:
                    log_message(f"  - ERROR: Could not delete {filename}: {e}")

        if deleted:
            log_message(f"Cleanup finished. Deleted {deleted} old log file(s). (scanned={scanned})")
        else:
            log_message(f"No old log files to clean up. (scanned={scanned}, cutoff={cutoff_date})")
    except Exception as e:
        log_message(f"ERROR: _cleanup_old_logs failed: {e}")
def _handle_rmtree_error(func, path, exc_info):
    """
    Error handler for shutil.rmtree that handles read-only files.
    If a file is read-only, it changes its permissions and retries the deletion.
    """
    # exc_info[1] is the exception object. We're interested in PermissionError.
    if isinstance(exc_info[1], PermissionError):
        try:
            # Make the file writable.
            os.chmod(path, stat.S_IWRITE)
            # Retry the function that failed (e.g., os.remove).
            func(path)
        except Exception as e:
            log_message(f"ERROR: Could not delete {path} even after removing read-only flag: {e}")
    else:
        log_message(f"ERROR: Deletion failed for {path}: {exc_info[1]}")

def show_notification(title, message, app_id="ezBAK", button_text=None, button_argument=None):
    """Shows a Windows toast notification with an optional button."""
    try:
        # Escape single quotes for PowerShell
        safe_title = title.replace("'", "''")
        safe_message = message.replace("'", "''")

        if button_text and button_argument:
            safe_button_text = button_text.replace("'", "''")
            # The argument for protocol activation is the path.
            # PowerShell should handle the path correctly.
            safe_button_argument = button_argument.replace("'", "''")
            
            # Using ToastGeneric template for actions.
            # The 'arguments' attribute will be executed by ShellExecute.
            # A folder path will open in Explorer.
            script = f"""
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            $template = @"
            <toast>
                <visual>
                    <binding template="ToastGeneric">
                        <text>{safe_title}</text>
                        <text>{safe_message}</text>
                    </binding>
                </visual>
                <actions>
                    <action
                        content="{safe_button_text}"
                        arguments="{safe_button_argument}"
                        activationType="protocol"/>
                </actions>
            </toast>
"@
            $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
            $xml.LoadXml($template)
            $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{app_id}').Show($toast)
            """
        else:
            # Original simple notification
            script = f"""
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
            $toastXml = $template.GetXml()
            $toastXml.GetElementsByTagName('text')[0].AppendChild($template.CreateTextNode('{safe_title}')) | Out-Null
            $toastXml.GetElementsByTagName('text')[1].AppendChild($template.CreateTextNode('{safe_message}')) | Out-Null
            $toastNotification = [Windows.UI.Notifications.ToastNotification]::new($toastXml)
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{app_id}').Show($toastNotification)
            """
        
        # Using -Command to execute the script block. shell=True is needed.
        # We don't wait for it and redirect output to DEVNULL to not pollute logs.
        subprocess.run(["powershell", "-Command", script], check=False, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log_message(f"INFO: Failed to show Windows notification: {e}")

def _find_available_drive_letter():
    """사용 가능한 드라이브 문자를 찾아 반환 (Z부터 역순으로)"""
    try:
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(25, 1, -1):  # Z부터 C까지 역순
            if not (bitmask & (1 << i)):
                return f"{chr(65 + i)}:"
    except Exception:
        # Fallback: 직접 확인
        for letter in "ZYXWVUTSRQPONMLKJIHGFEDC":
            if not os.path.exists(f"{letter}:\\"):
                return f"{letter}:"
    return None

try:
    import win32api
    import win32con
    _have_pywin32 = True
except Exception:
    win32api = None
    win32con = None
    _have_pywin32 = False
    FILE_ATTRIBUTE_HIDDEN = 0x02
    FILE_ATTRIBUTE_SYSTEM = 0x04
    FILE_ATTRIBUTE_REPARSE_POINT = 0x400
    try:
        from ctypes import wintypes
        _GetFileAttributesW = ctypes.windll.kernel32.GetFileAttributesW
        _GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
        _GetFileAttributesW.restype = wintypes.DWORD
        def _get_file_attributes(path):
            res = _GetFileAttributesW(path)
            if res == 0xFFFFFFFF: raise OSError(f"GetFileAttributesW failed for {path}")
            return int(res)
    except Exception:
        def _get_file_attributes(path): raise OSError("GetFileAttributesW unavailable")

class HeadlessBackupRunner:
    """Performs backup operations in headless mode based on a config dictionary."""
    def __init__(self, config_data):
        self.config = config_data
        self.task_name = self.config.get('task_name', 'UnknownTask')
        self.dest = self.config.get('dest')
        self.hidden_mode = 'include' if self.config.get('include_hidden') else 'exclude'
        self.system_mode = 'include' if self.config.get('include_system') else 'exclude'
        self.retention_count = int(self.config.get('retention_count', 2))
        self.log_retention_days = int(self.config.get('log_retention_days', 30))
        
        # Load filters
        fobj = self.config.get('filters', {})
        inc = fobj.get('include', []) if isinstance(fobj, dict) else []
        exc = fobj.get('exclude', []) if isinstance(fobj, dict) else []
        self.filters = {'include': inc, 'exclude': exc}
        self.direct_ftp = self.config.get('direct_ftp', False)

    def _get_base_name(self):
        """Determines the base name for backup folder and cleanup prefix."""
        backup_type = self.config.get('type')
        if backup_type == 'user_profile':
            # 사용자 프로필 백업의 경우, 작업 이름 대신 사용자 이름을 기본 이름으로 사용합니다.
            # 예: Public_backup_2024-09-16
            return self.config.get('user', 'UnknownUser')

        # 'custom_copy' 타입이고 작업 이름이 기본값인 'ezBAK_Custom_Backup'일 경우,
        # 폴더 및 로그 이름의 기반을 'Custom'으로 줄여서 사용합니다.
        if backup_type == 'custom_copy' and self.task_name == 'ezBAK_Custom_Backup':
            return 'Custom'

        # 그 외 모든 경우(사용자가 직접 지정한 작업 이름 등)에는 작업 이름 전체를 사용합니다.
        return self.task_name

    def _matches(self, pattern, text):
        """Case-insensitive fnmatch helper"""
        return fnmatch.fnmatch(text.lower(), pattern.lower())

    def is_hidden(self, filepath):
        if not os.path.exists(filepath): return False
        
        name = os.path.basename(filepath)
        
        # 1. Check Include Rules (Priority)
        # If explicitly included, we skip hidden/system checks? 
        # Usually "Include" overrides "Exclude", but does it override "Hidden attribute"?
        # In ezBAK logic, is_hidden_safe returns False (not hidden) if included.
        for rule in self.filters['include']:
            rtype = rule.get('type')
            pat = rule.get('pattern')
            if not pat: continue
            
            if rtype == 'ext':
                if name.lower().endswith(f".{pat.lower()}"): return False
            elif rtype == 'name':
                if self._matches(pat, name): return False
            elif rtype == 'path':
                if self._matches(pat, filepath): return False

        # 2. Check Exclude Rules
        for rule in self.filters['exclude']:
            rtype = rule.get('type')
            pat = rule.get('pattern')
            if not pat: continue
            
            if rtype == 'ext':
                if name.lower().endswith(f".{pat.lower()}"): return True
            elif rtype == 'name':
                if self._matches(pat, name): return True
            elif rtype == 'path':
                if self._matches(pat, filepath): return True

        # 3. Standard Hidden/System Checks
        base = name.lower()
        
        # Default exclusions (matches ezBAK behavior)
        if base.startswith('onedrive') or base.startswith('.') or base in ('thumbs.db', 'desktop.ini', '$recycle.bin', 'pagefile.sys', 'swapfile.sys', 'hiberfil.sys', 'dumpstack.log.tmp'):
            return True
            
        if base in ('appdata', 'application data', 'local settings'):
            if not (self.hidden_mode == 'include' and self.system_mode == 'include'):
                return True
        try:
            if _have_pywin32 and win32api:
                attrs = win32api.GetFileAttributes(filepath)
                is_hidden_attr = bool(attrs & win32con.FILE_ATTRIBUTE_HIDDEN)
                is_system_attr = bool(attrs & win32con.FILE_ATTRIBUTE_SYSTEM)
                is_reparse = bool(attrs & win32con.FILE_ATTRIBUTE_REPARSE_POINT)
            else:
                attrs = _get_file_attributes(filepath)
                is_hidden_attr = bool(attrs & FILE_ATTRIBUTE_HIDDEN)
                is_system_attr = bool(attrs & FILE_ATTRIBUTE_SYSTEM)
                is_reparse = bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)
            if is_reparse: return True
            if is_hidden_attr and self.hidden_mode == 'exclude': return True
            if is_system_attr and self.system_mode == 'exclude': return True
        except Exception as e:
            # Suppress "process cannot access file" (WinError 32) and similar locking errors
            # If we can't check attributes, we likely can't copy it either, so treating as "not hidden" 
            # (returning False) will let the copy logic try and fail (logging the copy error), 
            # or we could return True to skip. 
            # Given these are usually system files, skipping might be safer, but let's just suppress the log.
            if getattr(e, 'winerror', 0) == 32:
                return True # Skip locked files during attribute check to avoid noise
            log_message(f"WARN: is_hidden check failed for {filepath}: {e}")
        return False

    def copy_file_with_progress(self, src, dst, progress_callback, buffer_size=64*1024):
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            copied = 0
            with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
                while True:
                    buf = fsrc.read(buffer_size)
                    if not buf: break
                    fdst.write(buf)
                    copied += len(buf)
                    progress_callback(len(buf))
            try: shutil.copystat(src, dst)
            except Exception: pass
            return copied
        except Exception as e:
            log_message(f"ERROR: copying file {src} -> {dst}: {e}")
            return 0

    def compute_total_bytes(self, root_path):
        total = 0
        for dirpath, dirnames, filenames in os.walk(root_path, topdown=True, onerror=lambda e: None):
            dirnames[:] = [d for d in dirnames if not self.is_hidden(os.path.join(dirpath, d))]
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not self.is_hidden(fp):
                    try: total += os.path.getsize(fp)
                    except Exception: pass
        return total

    def run_backup(self):
        backup_type = self.config.get('type')
        if backup_type == 'user_profile':
            self._run_user_profile_backup()
        elif backup_type == 'custom_copy':
            self._run_custom_copy_backup()
        elif backup_type == 'data_sync':
            self._run_data_sync_backup()
        else:
            log_message(f"ERROR: Unknown backup type '{backup_type}' in config.")

    def _prepare_backup(self):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        base_name = self._get_base_name()
        destination_dir = os.path.join(self.dest, f"{base_name}_backup_{timestamp}")
        log_message(f"Backup for task: {self.task_name}")
        log_message(f"Destination: {destination_dir}")
        log_message(f"Policy: Hidden={self.hidden_mode}, System={self.system_mode}, BackupKeep={self.retention_count}, LogKeep={self.log_retention_days}")
        
        inc_str = ", ".join([f"{r['type']}:{r['pattern']}" for r in self.filters['include']]) or "None"
        exc_str = ", ".join([f"{r['type']}:{r['pattern']}" for r in self.filters['exclude']]) or "None"
        log_message(f"Filters: Include=[{inc_str}], Exclude=[{exc_str}]")
        
        log_message("-" * 50)

        if self.direct_ftp:
            destination_dir = tempfile.mkdtemp(prefix=f"{base_name}_backup_{timestamp}_")
            log_message(f"Direct FTP-Transfer enabled. Using temporary folder: {destination_dir}")
        else:
            destination_dir = os.path.join(self.dest, f"{base_name}_backup_{timestamp}")
            if os.path.exists(destination_dir):
                try: shutil.rmtree(destination_dir)
                except Exception as e: log_message(f"WARN: Failed to delete existing backup folder '{destination_dir}': {e}")
            os.makedirs(destination_dir, exist_ok=True)
            
        return destination_dir

    def _run_user_profile_backup(self):
        user_name = self.config.get('user')
        if not user_name:
            log_message("ERROR: 'user' not specified in config for user_profile backup.")
            return

        user_profile_path = os.path.join("C:", os.sep, "Users", user_name)
        if not os.path.exists(user_profile_path):
            log_message(f"ERROR: User folder '{user_profile_path}' not found.")
            return

        destination_dir = self._prepare_backup()
        total_bytes = self.compute_total_bytes(user_profile_path)
        self._execute_copy(total_bytes, [user_profile_path], destination_dir, is_user_profile=True)

    def _run_custom_copy_backup(self):
        sources = self.config.get('sources', [])
        if not sources:
            log_message("ERROR: 'sources' not specified in config for custom_copy backup.")
            return

        destination_dir = self._prepare_backup()
        total_bytes = 0
        for path in sources:
            if os.path.isdir(path): total_bytes += self.compute_total_bytes(path)
            elif os.path.isfile(path) and not self.is_hidden(path):
                try: total_bytes += os.path.getsize(path)
                except Exception: pass
        self._execute_copy(total_bytes, sources, destination_dir, is_user_profile=False)

    def _run_data_sync_backup(self):
        """데이터 동기화: 소스 폴더들을 대상 폴더와 동기화"""
        sources = self.config.get('sources', [])
        if not sources:
            log_message("ERROR: 'sources' not specified in config for data_sync backup.")
            return

        log_message(f"Data Sync for task: {self.task_name}")
        
        if self.direct_ftp:
            dest_root = tempfile.mkdtemp(prefix=f"Sync_{self.task_name}_")
            log_message(f"Direct FTP-Transfer enabled. Using temporary folder: {dest_root}")
        else:
            dest_root = self.dest
            # Ensure drive letter has trailing slash (e.g., "Z:" -> "Z:\")
            if len(dest_root) == 2 and dest_root[1] == ':':
                dest_root += os.sep
            log_message(f"Destination: {dest_root}")

        log_message(f"Policy: Hidden={self.hidden_mode}, System={self.system_mode}, LogKeep={self.log_retention_days}")
        
        inc_str = ", ".join([f"{r['type']}:{r['pattern']}" for r in self.filters['include']]) or "None"
        exc_str = ", ".join([f"{r['type']}:{r['pattern']}" for r in self.filters['exclude']]) or "None"
        log_message(f"Filters: Include=[{inc_str}], Exclude=[{exc_str}]")
        
        log_message("-" * 50)

        total_files_synced = 0
        total_bytes_synced = 0
        files_added = 0
        files_updated = 0
        files_deleted = 0

        files_deleted = 0
        
        synced_items = []

        log_message("[Sync operations]")
        
        for source in sources:
            if not os.path.exists(source):
                log_message(f"WARN: Source path does not exist: {source}")
                continue

            # 소스의 베이스 이름을 대상 경로에 사용
            base_name = os.path.basename(source.rstrip("\\/"))
            if not base_name:
                drive, _ = os.path.splitdrive(source)
                base_name = (drive.rstrip(':') or 'root') + "_drive"
            
            synced_items.append(base_name)
            
            dest_path = os.path.join(dest_root, base_name)
            
            if os.path.isfile(source):
                # 단일 파일 동기화
                if self.is_hidden(source):
                    continue
                    
                os.makedirs(dest_root, exist_ok=True)
                dest_file = os.path.join(dest_root, base_name)
                
                if self._sync_file(source, dest_file):
                    if not os.path.exists(dest_file):
                        files_added += 1
                        log_message(f"[ADD] {source}")
                    else:
                        files_updated += 1
                        log_message(f"[UPDATE] {source}")
                    try:
                        total_bytes_synced += os.path.getsize(source)
                    except Exception:
                        pass
                    total_files_synced += 1
                    
            elif os.path.isdir(source):
                # 디렉토리 동기화
                log_message(f"Syncing directory: {source} -> {dest_path}")
                
                # 소스 파일 목록 생성
                source_files = {}
                for dirpath, dirnames, filenames in os.walk(source, topdown=True):
                    dirnames[:] = [d for d in dirnames if not self.is_hidden(os.path.join(dirpath, d))]
                    
                    for filename in filenames:
                        src_file = os.path.join(dirpath, filename)
                        if self.is_hidden(src_file):
                            continue
                        rel_path = os.path.relpath(src_file, source)
                        source_files[rel_path] = src_file
                
                # 대상 폴더가 존재하면 기존 파일 확인
                dest_files = set()
                if os.path.exists(dest_path):
                    for dirpath, dirnames, filenames in os.walk(dest_path):
                        for filename in filenames:
                            dest_file = os.path.join(dirpath, filename)
                            rel_path = os.path.relpath(dest_file, dest_path)
                            dest_files.add(rel_path)
                
                # 소스 파일 동기화 (추가 및 업데이트)
                for rel_path, src_file in source_files.items():
                    dest_file = os.path.join(dest_path, rel_path)
                    dest_dir = os.path.dirname(dest_file)
                    os.makedirs(dest_dir, exist_ok=True)
                    
                    is_new = rel_path not in dest_files
                    if self._sync_file(src_file, dest_file):
                        if is_new:
                            files_added += 1
                            log_message(f"[ADD] {rel_path}")
                        else:
                            files_updated += 1
                            log_message(f"[UPDATE] {rel_path}")
                        try:
                            total_bytes_synced += os.path.getsize(src_file)
                        except Exception:
                            pass
                        total_files_synced += 1
                
                # 대상에만 있는 파일 삭제
                for rel_path in dest_files:
                    if rel_path not in source_files:
                        dest_file = os.path.join(dest_path, rel_path)
                        try:
                            os.remove(dest_file)
                            files_deleted += 1
                            log_message(f"[DELETE] {rel_path}")
                        except Exception as e:
                            log_message(f"WARN: Could not delete {dest_file}: {e}")

                # 빈 디렉토리 정리 (Bottom-up)
                for dirpath, dirnames, filenames in os.walk(dest_path, topdown=False):
                    rel_dir = os.path.relpath(dirpath, dest_path)
                    if rel_dir == '.': continue
                    
                    src_dir = os.path.join(source, rel_dir)
                    if not os.path.exists(src_dir):
                        try:
                            os.rmdir(dirpath)
                            log_message(f"[DELETE DIR] {rel_dir}")
                        except OSError:
                            # 디렉토리가 비어있지 않으면 삭제하지 않음 (정상)
                            pass

        log_message("-" * 50)
        log_message(f"Sync completed.")
        log_message(f"  Files added: {files_added}")
        log_message(f"  Files updated: {files_updated}")
        log_message(f"  Files deleted: {files_deleted}")
        log_message(f"  Total synced: {total_files_synced} files ({format_bytes(total_bytes_synced)})")
        log_message("-" * 50)

        # 로그 정리
        # 로그 정리
        base_name = self._get_base_name()
        log_prefix = f"{base_name}_sync_"
        if not self.direct_ftp:
            _cleanup_old_logs(dest_root, self.log_retention_days, log_prefix)

        # --- FTP Transfer ---
        if self.direct_ftp:
             self._upload_to_ftp(dest_root)
        else:
             log_message(f"FTP Transfer: Uploading synced items: {synced_items}")
             self._upload_to_ftp(dest_root, items=synced_items)

        if self.direct_ftp:
            log_message(f"Direct FTP-Transfer: Deleting temporary sync folder: {dest_root}")
            try:
                shutil.rmtree(dest_root, onerror=_handle_rmtree_error)
            except Exception as e:
                log_message(f"WARN: Failed to delete temporary folder: {e}")

        show_notification(
            title="ezBAK Data Sync Complete",
            message=f"Task '{self.task_name}' finished successfully.\n+{files_added} ~{files_updated} -{files_deleted} ({format_bytes(total_bytes_synced)}).",
            button_text="Open Folder",
            button_argument=dest_root if not self.direct_ftp else ""
        )

        # 이메일 알림 전송
        email_config = self.config.get('email_notification', {})
        if email_config.get('enabled') and email_config.get('notify_on_success'):
            log_message("Sending success notification email...")
            try:
                email_subject = f"[SUCCESS] ezBAK Data Sync Completed: {self.task_name}"
                email_body = (
                    f"The scheduled data sync task '{self.task_name}' completed successfully.\n\n"
                    f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Destination: {self.dest}\n"
                    f"Files added: {files_added}\n"
                    f"Files updated: {files_updated}\n"
                    f"Files deleted: {files_deleted}\n"
                    f"Total synced: {total_files_synced} files\n"
                    f"Total size: {format_bytes(total_bytes_synced)}\n\n"
                    f"Log retention policy: Keep logs for {self.log_retention_days} days"
                )
                send_email_notification(email_subject, email_body, email_config)
            except Exception as email_e:
                log_message(f"ERROR: Could not send success email notification: {email_e}")

    def _sync_file(self, src, dest):
        """파일을 동기화합니다. 변경된 경우에만 복사하고 True 반환"""
        try:
            # 대상 파일이 없거나, 크기나 수정 시간이 다르면 복사
            if not os.path.exists(dest):
                shutil.copy2(src, dest)
                return True
            
            src_stat = os.stat(src)
            dest_stat = os.stat(dest)
            
            # 크기가 다르거나 수정 시간이 더 새로운 경우 복사
            if (src_stat.st_size != dest_stat.st_size or 
                src_stat.st_mtime > dest_stat.st_mtime):
                shutil.copy2(src, dest)
                return True
                
            return False  # 동일한 파일, 복사 불필요
            
        except Exception as e:
            log_message(f"ERROR: Failed to sync file {src}: {e}")
            return False

    def _upload_to_ftp(self, source_dir, items=None):
        """Uploads the backup to an FTP server if configured.
        
        Args:
            source_dir (str): The local directory containing files to upload.
            items (list, optional): A list of specific file/folder names in source_dir to upload.
                                    If None, uploads everything in source_dir.
        """
        ftp_config = self.config.get('ftp_transfer', {})
        if not ftp_config.get('enabled'):
            return

        host = ftp_config.get('host', '').strip()
        port = int(ftp_config.get('port', '21'))
        user = ftp_config.get('user', '').strip()
        password = _decrypt_password(ftp_config.get('password', ''))
        remote_path = ftp_config.get('remote_path', '/').strip()

        if not host:
            log_message("WARN: FTP transfer enabled but host is empty.")
            return

        log_message("-" * 50)
        log_message(f"Starting FTP transfer to: {host}")

        ftp = None
        try:
            ftp = ftplib.FTP()
            ftp.connect(host, port)
            ftp.login(user, password)
            log_message(f"Connected to FTP: {host}")

            # Change to remote path, create if not exists
            try:
                ftp.cwd(remote_path)
            except ftplib.error_perm:
                log_message(f"Remote path '{remote_path}' not found. Attempting to create...")
                try:
                    ftp.mkd(remote_path)
                    ftp.cwd(remote_path)
                except Exception as e:
                    raise Exception(f"Could not create/navigate to remote path: {e}")

            # Determine backup folder name
            if self.direct_ftp:
                # Direct FTP: Upload contents directly to remote_path
                # Do not create a subfolder for the backup itself
                ftp.cwd(remote_path)
            else:
                # Normal Backup: Create a subfolder for this specific backup
                backup_folder_name = os.path.basename(source_dir.rstrip(os.sep))
                if backup_folder_name:
                    try:
                        ftp.mkd(backup_folder_name)
                    except ftplib.error_perm:
                        pass
                    ftp.cwd(backup_folder_name)
            
            # Upload files
            files_uploaded = 0
            
            # Determine what to upload: specific items or everything
            items_to_process = items if items is not None else os.listdir(source_dir)
            
            for item_name in items_to_process:
                item_path = os.path.join(source_dir, item_name)
                if not os.path.exists(item_path):
                    continue
                if self.is_hidden(item_path):
                    continue

                # Calculate remote path for this item
                # If direct_ftp, we are in remote_path. item_name is the file/folder in remote_path.
                # If normal backup, we are in backup_folder_name. item_name is file/folder there.
                # In both cases, we just need to process item_name relative to current CWD.
                
                if os.path.isdir(item_path):
                    # Sync directory recursively
                    files_uploaded += self._sync_ftp_folder(ftp, item_path, item_name)

                elif os.path.isfile(item_path):
                    # Upload single file
                    log_message(f"Uploading: {item_name}")
                    with open(item_path, 'rb') as f:
                        ftp.storbinary(f'STOR {item_name}', f)
                    files_uploaded += 1

            log_message("FTP transfer completed successfully.")
            
            # Send Success Email
            email_config = self.config.get('email_notification', {})
            log_message(f"Checking email config for FTP success: enabled={email_config.get('enabled')}, notify_on_success={email_config.get('notify_on_success')}")
            if email_config.get('enabled') and email_config.get('notify_on_success'):
                subject = f"[SUCCESS] ezBAK FTP Transfer Completed: {self.task_name}"
                body = (f"FTP Transfer for task '{self.task_name}' completed successfully.\n"
                        f"Host: {host}\n"
                        f"Files uploaded: {files_uploaded}")
                send_email_notification(subject, body, email_config)

        except Exception as e:
            log_message(f"ERROR: FTP transfer failed: {e}")
            # Send Failure Email
            email_config = self.config.get('email_notification', {})
            if email_config.get('enabled') and email_config.get('notify_on_failure', True):
                subject = f"[FAIL] ezBAK FTP Transfer Failed: {self.task_name}"
                body = (f"FTP Transfer for task '{self.task_name}' failed.\n"
                        f"Host: {host}\n"
                        f"Error: {e}")
                send_email_notification(subject, body, email_config)
            
        finally:
            if ftp:
                try:
                    ftp.quit()
                except:
                    try: ftp.close()
                    except: pass

    def _sync_ftp_folder(self, ftp, local_folder, remote_folder_name):
        """Recursively syncs a local folder to the FTP server (Upload + Delete)."""
        uploaded_count = 0
        
        # 1. Ensure remote folder exists and enter it
        try:
            ftp.cwd(remote_folder_name)
        except ftplib.error_perm:
            try:
                ftp.mkd(remote_folder_name)
                ftp.cwd(remote_folder_name)
            except Exception as e:
                log_message(f"ERROR: Could not create/enter remote folder {remote_folder_name}: {e}")
                return 0

        # 2. List remote files/folders
        remote_items = []
        try:
            remote_items = ftp.nlst()
        except ftplib.error_perm:
            # Empty directory or permission error
            pass
            
        # Exclude . and ..
        remote_items = [i for i in remote_items if i not in ('.', '..')]

        # 3. List local files/folders
        local_items = os.listdir(local_folder)
        local_items_set = set()
        
        for item in local_items:
            local_path = os.path.join(local_folder, item)
            if self.is_hidden(local_path): continue
            local_items_set.add(item)
            
            if os.path.isdir(local_path):
                uploaded_count += self._sync_ftp_folder(ftp, local_path, item)
            elif os.path.isfile(local_path):
                # Upload file (overwrite)
                # Optimization: Check size/mtime if possible? 
                # For now, simple overwrite to ensure consistency.
                log_message(f"Uploading: {item}")
                try:
                    with open(local_path, 'rb') as f:
                        ftp.storbinary(f'STOR {item}', f)
                    uploaded_count += 1
                except Exception as e:
                    log_message(f"ERROR: Failed to upload {item}: {e}")

        # 4. Delete remote items that are not in local
        for item in remote_items:
            if item not in local_items_set:
                log_message(f"Deleting remote item (not in local): {item}")
                self._delete_ftp_item(ftp, item)

        # 5. Go back up
        ftp.cwd('..')
        return uploaded_count

    def _delete_ftp_item(self, ftp, item):
        """Deletes a file or directory (recursively) on FTP."""
        try:
            # Try deleting as file first
            ftp.delete(item)
        except ftplib.error_perm:
            # Likely a directory, try recursive delete
            try:
                current_dir = ftp.pwd()
                try:
                    ftp.cwd(item)
                    sub_items = ftp.nlst()
                    for sub in sub_items:
                        if sub in ('.', '..'): continue
                        self._delete_ftp_item(ftp, sub)
                    ftp.cwd(current_dir)
                    ftp.rmd(item)
                except Exception as e:
                    log_message(f"ERROR: Failed to delete remote directory {item}: {e}")
                    ftp.cwd(current_dir) # Ensure we are back
            except Exception as e:
                log_message(f"ERROR: Failed to delete remote item {item}: {e}")

    def _execute_copy(self, total_bytes, sources, destination_dir, is_user_profile):
        log_message(f"Calculating total size... {format_bytes(total_bytes)}")
        
        if not self.direct_ftp:
            try:
                free = shutil.disk_usage(self.dest).free
                if total_bytes > free:
                    log_message(f"ERROR: Insufficient free space. Required: {format_bytes(total_bytes)}, Available: {format_bytes(free)}")
                    return
            except Exception as e:
                log_message(f"WARN: Could not check disk space: {e}")

        bytes_copied = 0
        files_processed = 0
        def progress_cb(delta): nonlocal bytes_copied; bytes_copied += delta

        log_message("[Backed up items list]")
        for source in sources:
            if is_user_profile:
                dest_path_root = destination_dir
            else:
                base = os.path.basename(source.rstrip("\\/"))
                if not base:
                    drive, _ = os.path.splitdrive(source)
                    base = (drive.rstrip(':') or 'root') + "_drive"
                dest_path_root = os.path.join(destination_dir, base)

            if os.path.isdir(source):
                log_message(f"Copying directory: {source}")
                for dirpath, dirnames, filenames in os.walk(source, topdown=True, onerror=lambda e: log_message(f"WARN: os.walk error: {e}")):
                    dirnames[:] = [d for d in dirnames if not self.is_hidden(os.path.join(dirpath, d))]

                    # Ensure destination directory exists, even if it's empty
                    rel_dir = os.path.relpath(dirpath, source)
                    dest_dir = os.path.join(dest_path_root, rel_dir) if rel_dir != '.' else dest_path_root
                    os.makedirs(dest_dir, exist_ok=True)

                    for f in filenames:
                        src_file = os.path.join(dirpath, f)
                        if self.is_hidden(src_file): continue
                        dest_file = os.path.join(dest_dir, f)
                        log_message(os.path.relpath(src_file, source)) # Log original relative path
                        self.copy_file_with_progress(src_file, dest_file, progress_cb)
                        files_processed += 1
            elif os.path.isfile(source):
                if self.is_hidden(source): continue
                log_message(f"Copying file: {source}")
                self.copy_file_with_progress(source, dest_path_root, progress_cb)
                files_processed += 1

        log_message("-" * 50)
        log_message(f"Backup completed.")
        log_message(f"  Files backed up: {files_processed}")
        log_message(f"  Total size: {format_bytes(bytes_copied)}")
        log_message(f"  Total size: {format_bytes(bytes_copied)}")
        log_message("-" * 50)
        
        if not self.direct_ftp:
            base_name = self._get_base_name()
            self._cleanup_old_backups(self.dest, base_name)
            
            log_prefix = f"{base_name}_backup_"
            _cleanup_old_logs(self.dest, self.log_retention_days, log_prefix)

        # --- FTP Transfer ---
        # Upload only the current backup folder, not the entire destination root
        self._upload_to_ftp(destination_dir)

        if self.direct_ftp:
            log_message(f"Direct FTP-Transfer: Deleting temporary backup folder: {destination_dir}")
            try:
                shutil.rmtree(destination_dir, onerror=_handle_rmtree_error)
            except Exception as e:
                log_message(f"WARN: Failed to delete temporary folder: {e}")

        show_notification(
            title="ezBAK Backup Complete",
            message=f"Task '{self.task_name}' finished successfully.\n{files_processed} files synced ({format_bytes(bytes_copied)}).",
            button_text="Open Folder",
            button_argument=self.dest
        )

        # --- Send success email notification if enabled ---
        email_config = self.config.get('email_notification', {})
        if email_config.get('enabled') and email_config.get('notify_on_success'):
            log_message("Sending success notification email...")
            try:
                email_subject = f"[SUCCESS] ezBAK Backup Completed: {self.task_name}"
                email_body = (
                    f"The scheduled backup task '{self.task_name}' completed successfully.\n\n"
                    f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Destination: {destination_dir}\n"
                    f"Files backed up: {files_processed}\n"
                    f"Total size: {format_bytes(bytes_copied)}\n\n"
                    f"Backup retention policy: Keep {self.retention_count} backup(s)\n"
                    f"Log retention policy: Keep logs for {self.log_retention_days} days"
                )
                send_email_notification(email_subject, email_body, email_config)
            except Exception as email_e:
                log_message(f"ERROR: Could not send success email notification: {email_e}")

    def _cleanup_old_backups(self, backup_path, base_name):
        try:
            if self.retention_count <= 0:
                log_message("[Old backup cleanup]\nBackup cleanup is disabled (retention count is 0 or less).")
                return
            log_message("[Old backup cleanup]")
            backup_prefix = f"{base_name}_backup_"
            all_backups = [d for d in os.listdir(backup_path) if os.path.isdir(os.path.join(backup_path, d)) and d.startswith(backup_prefix)]
            if len(all_backups) > self.retention_count:
                log_message(f"Found {len(all_backups)} backups. Keeping the {self.retention_count} most recent.")
                all_backups.sort()
                backups_to_delete = all_backups[:-self.retention_count]
                for backup_dir_name in backups_to_delete:
                    dir_to_delete = os.path.join(backup_path, backup_dir_name)
                    log_message(f"  Deleting old backup: {dir_to_delete}")
                    shutil.rmtree(dir_to_delete, onerror=_handle_rmtree_error)
                log_message("Cleanup finished.")
            else:
                log_message(f"Found {len(all_backups)} backups. No old backups to clean up (retention policy: keep {self.retention_count}).")
        except Exception as e:
            log_message(f"ERROR: An error occurred during backup cleanup: {e}")

class DialogShortcuts:
    """Common shortcut key functions for dialogs"""
    
    def setup_dialog_shortcuts(self):
        """Common Shortcut Key Features for Dialogs"""
        # Basic dialog shortcuts
        self.bind('<Escape>', lambda e: self.on_cancel() if hasattr(self, 'on_cancel') else self.destroy())
        self.bind('<Return>', lambda e: self.on_ok() if hasattr(self, 'on_ok') else None)
        self.bind('<Alt-F4>', lambda e: self.destroy())
        
        # Set focus (to receive keyboard events)
        self.focus_set()
        
    def add_shortcut_text(self, text, shortcut):
        """Add shortcut notation to text"""
        return f"{text} ({shortcut})"

class FilterManagerDialog(tk.Toplevel, DialogShortcuts):
    def __init__(self, master, current_filters=None):
        tk.Toplevel.__init__(self, master)
        self.parent = master
        self.title("Filter Manager")
        try:
            self.iconbitmap(resource_path('./icon/ezbak_title.ico'))
        except Exception:
            try: self.iconbitmap(resource_path('./icon/ezbak.ico'))
            except Exception: pass
            
        # Theme colors (hardcoded for ezSBAK)
        self.colors = {
            'bg': '#2D3250',
            'bg_elevated': '#424769',
            'fg': 'white',
            'fg_secondary': '#B0B0B0',
            'accent': '#336BFF',
            'accent_hover': '#254EDB',
            'danger': '#FF5733',
            'success': '#2E7D32',
            'border': '#555555',
            'hover': '#505575',
            'pressed': '#202540',
            'scrollbar_bg': '#424769'
        }
        
        self.configure(bg=self.colors['bg'])
        self.geometry("750x520")
        self.transient(master)
        try:
            self.grab_set()
        except Exception:
            pass

        self.result = None
        cf = current_filters or {'include': [], 'exclude': []}
        # deep copy simple
        self.inc = [dict(type=i.get('type'), pattern=i.get('pattern')) for i in (cf.get('include') or [])]
        self.exc = [dict(type=i.get('type'), pattern=i.get('pattern')) for i in (cf.get('exclude') or [])]

        self._create_filter_widgets()
        self._setup_filter_shortcuts()
        self._refresh()

    def _create_button(self, parent, text, command, is_primary=False, width=12):
        """Create a styled button"""
        if is_primary:
            btn_bg = self.colors['accent']
            btn_fg = '#FFFFFF'
            hover_bg = self.colors['accent_hover']
            hover_fg = '#FFFFFF'
            pressed_bg = self.colors['accent_hover']
        else:
            btn_bg = self.colors['bg_elevated']
            btn_fg = self.colors['fg']
            hover_bg = self.colors['hover']
            hover_fg = self.colors['fg']
            pressed_bg = self.colors['pressed']

        btn = tk.Button(parent, text=text,
                       command=command,
                       bg=btn_bg,
                       fg=btn_fg,
                       font=("Segoe UI", 9),
                       relief="flat",
                       bd=0,
                       width=width,
                       cursor="hand2",
                       padx=12,
                       pady=6)

        # Hover effects
        def on_enter(e):
            e.widget.config(bg=hover_bg, fg=hover_fg)
        def on_leave(e):
            e.widget.config(bg=btn_bg, fg=btn_fg)
        def on_press(e):
            e.widget.config(bg=pressed_bg)
        def on_release(e):
            e.widget.config(bg=hover_bg)

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        btn.bind("<ButtonPress-1>", on_press)
        btn.bind("<ButtonRelease-1>", on_release)

        return btn

    def _setup_filter_shortcuts(self):
        """Setup shortcuts specific to filter dialog"""
        self.setup_dialog_shortcuts()
        self.bind('<Control-n>', lambda e: self._add_rule('include'))
        self.bind('<Control-e>', lambda e: self._add_rule('exclude'))
        self.bind('<Delete>', lambda e: self._remove_selected_active())
        self.bind('<Control-s>', lambda e: self._save())
        self.bind('<Control-r>', lambda e: self._clear_active())
        self.bind('<F1>', lambda e: self._show_filter_help())
        self.bind('<Tab>', lambda e: self._cycle_focus())
        
    def _cycle_focus(self):
        try:
            focused = self.focus_get()
            if focused == self.inc_list:
                self.exc_list.focus_set()
            else:
                self.inc_list.focus_set()
        except Exception:
            self.inc_list.focus_set()

    def _create_filter_widgets(self):
        # Top description
        info_frame = tk.Frame(self, bg=self.colors['bg'])
        info_frame.pack(fill='x', padx=12, pady=(12,6))

        info_text = "Manage file/folder filters. 'Include' rules take precedence over 'Exclude' rules."
        tk.Label(info_frame, text=info_text, bg=self.colors['bg'], fg=self.colors['fg_secondary'],
                font=("Arial", 9), justify='left').pack(anchor='w')

        # Layout
        top = tk.Frame(self, bg=self.colors['bg'])
        top.pack(fill='both', expand=True, padx=12, pady=6)

        # Include panel
        inc_frame = tk.LabelFrame(top, text=self.add_shortcut_text("Include Rules", "Ctrl+N"),
                                 bg=self.colors['bg'], fg=self.colors['fg'], font=("Arial", 10, "bold"))
        inc_frame.pack(side='left', fill='both', expand=True, padx=(0,6))

        self.inc_list = tk.Listbox(inc_frame, height=14, font=("Consolas", 9),
                                  bg=self.colors['bg_elevated'], fg=self.colors['fg'], selectbackground=self.colors['success'])
        self.inc_list.pack(fill='both', expand=True, padx=6, pady=6)

        btn_row_inc = tk.Frame(inc_frame, bg=self.colors['bg'])
        btn_row_inc.pack(fill='x', padx=6, pady=(0,6))

        self._create_button(btn_row_inc, "Add", lambda: self._add_rule('include'), width=8).pack(side='left', padx=2)
        self._create_button(btn_row_inc, self.add_shortcut_text("Remove", "Del"), lambda: self._remove_selected('include'), width=12).pack(side='left', padx=2)
        self._create_button(btn_row_inc, "Clear All", lambda: self._clear('include'), width=10).pack(side='left', padx=2)

        # Exclude panel
        exc_frame = tk.LabelFrame(top, text=self.add_shortcut_text("Exclude Rules", "Ctrl+E"),
                                 bg=self.colors['bg'], fg=self.colors['fg'], font=("Arial", 10, "bold"))
        exc_frame.pack(side='left', fill='both', expand=True, padx=(6,0))

        self.exc_list = tk.Listbox(exc_frame, height=14, font=("Consolas", 9),
                                  bg=self.colors['bg_elevated'], fg=self.colors['fg'], selectbackground=self.colors['danger'])
        self.exc_list.pack(fill='both', expand=True, padx=6, pady=6)

        btn_row_exc = tk.Frame(exc_frame, bg=self.colors['bg'])
        btn_row_exc.pack(fill='x', padx=6, pady=(0,6))

        self._create_button(btn_row_exc, "Add", lambda: self._add_rule('exclude'), width=8).pack(side='left', padx=2)
        self._create_button(btn_row_exc, self.add_shortcut_text("Remove", "Del"), lambda: self._remove_selected('exclude'), width=12).pack(side='left', padx=2)
        self._create_button(btn_row_exc, "Clear All", lambda: self._clear('exclude'), width=10).pack(side='left', padx=2)

        # Bottom shortcut guide
        shortcut_frame = tk.Frame(self, bg=self.colors['bg'])
        shortcut_frame.pack(fill='x', padx=12, pady=(6,0))

        shortcut_text = "F1: Help  •  Tab: Switch Lists  •  Del: Remove Selected  •  Ctrl+R: Clear Active List"
        tk.Label(shortcut_frame, text=shortcut_text, bg=self.colors['bg'], fg=self.colors['fg_secondary'],
                font=("Arial", 8)).pack(anchor='w')

        # Bottom actions
        actions = tk.Frame(self, bg=self.colors['bg'])
        actions.pack(fill='x', padx=12, pady=12)

        self._create_button(actions, self.add_shortcut_text("Help", "F1"), self._show_filter_help, width=10).pack(side='left')
        self._create_button(actions, self.add_shortcut_text("Save", "Ctrl+S"), self._save, is_primary=True, width=12).pack(side='right')
        self._create_button(actions, self.add_shortcut_text("Cancel", "Esc"), self._cancel, width=12).pack(side='right', padx=(0,8))

    def _rule_to_text(self, r):
        try:
            rule_type = r.get('type', 'unknown')
            pattern = r.get('pattern', '')
            type_icons = {'ext': '📄', 'name': '📁', 'path': '🗂️'}
            icon = type_icons.get(rule_type, '❓')
            return f"{icon} [{rule_type.upper()}] {pattern}"
        except Exception:
            return str(r)

    def _refresh(self):
        self.inc_list.delete(0, tk.END)
        for r in self.inc: self.inc_list.insert(tk.END, self._rule_to_text(r))
        self.exc_list.delete(0, tk.END)
        for r in self.exc: self.exc_list.insert(tk.END, self._rule_to_text(r))

    def _remove_selected(self, kind):
        lst = self.inc_list if kind == 'include' else self.exc_list
        target = self.inc if kind == 'include' else self.exc
        idxs = list(lst.curselection())
        for i in reversed(idxs):
            if 0 <= i < len(target): del target[i]
        self._refresh()

    def _remove_selected_active(self):
        try:
            focused = self.focus_get()
            if focused == self.inc_list: self._remove_selected('include')
            elif focused == self.exc_list: self._remove_selected('exclude')
        except Exception: pass

    def _clear(self, kind):
        if kind == 'include': self.inc = []
        else: self.exc = []
        self._refresh()

    def _clear_active(self):
        try:
            focused = self.focus_get()
            if focused == self.inc_list: self._clear('include')
            elif focused == self.exc_list: self._clear('exclude')
        except Exception: pass

    def _add_rule(self, kind):
        dlg = tk.Toplevel(self)
        dlg.title("Add Include Rule" if kind == 'include' else "Add Exclude Rule")
        try:
            dlg.iconbitmap(resource_path('./icon/ezbak_title.ico'))
        except Exception:
            try: dlg.iconbitmap(resource_path('./icon/ezbak.ico'))
            except Exception: pass
        dlg.configure(bg=self.colors['bg'])
        dlg.geometry("480x320")
        dlg.transient(self)
        try: dlg.grab_set()
        except Exception: pass

        tk.Label(dlg, text="Rule Type", bg=self.colors['bg'], fg=self.colors['fg'],
                font=("Arial", 10, "bold")).pack(anchor='w', padx=15, pady=(15,5))

        vtype = tk.StringVar(value='ext')
        tframe = tk.Frame(dlg, bg=self.colors['bg'])
        tframe.pack(anchor='w', padx=15, fill='x')

        type_options = [
            ('ext', '📄 Extension', 'e.g. tmp, log, bak'),
            ('name', '📁 Name', 'e.g. node_modules, .git'),
            ('path', '🗂️ Full Path', 'e.g. C:\\Temp\\*')
        ]

        for value, label, desc in type_options:
            rb_frame = tk.Frame(tframe, bg=self.colors['bg'])
            rb_frame.pack(anchor='w', pady=2)
            tk.Radiobutton(rb_frame, text=label, variable=vtype, value=value,
                          bg=self.colors['bg'], fg=self.colors['fg'], selectcolor=self.colors['bg'],
                          font=("Arial", 9, "bold")).pack(side='left')
            tk.Label(rb_frame, text=f"  {desc}", bg=self.colors['bg'], fg=self.colors['fg_secondary'],
                    font=("Arial", 8)).pack(side='left')

        tk.Label(dlg, text="Pattern", bg=self.colors['bg'], fg=self.colors['fg'],
                font=("Arial", 10, "bold")).pack(anchor='w', padx=15, pady=(15,5))

        vpat = tk.StringVar()
        pat_frame = tk.Frame(dlg, bg=self.colors['bg'])
        pat_frame.pack(fill='x', padx=15)
        ent = tk.Entry(pat_frame, textvariable=vpat, width=50, font=("Arial", 10),
                      bg=self.colors['bg_elevated'], fg=self.colors['fg'], insertbackground=self.colors['fg'])
        ent.pack(fill='x')
        ent.focus_set()

        btns = tk.Frame(dlg, bg=self.colors['bg'])
        btns.pack(fill='x', padx=15, pady=15)

        def _ok():
            p = vpat.get().strip()
            if not p:
                messagebox.showwarning("Warning", "Please enter a pattern.", parent=dlg)
                return
            rule = {'type': vtype.get().strip().lower(), 'pattern': p}
            if kind == 'include': self.inc.append(rule)
            else: self.exc.append(rule)
            self._refresh()
            dlg.destroy()

        self._create_button(btns, "Add Rule", _ok, is_primary=True).pack(side='right')
        self._create_button(btns, "Cancel", dlg.destroy).pack(side='right', padx=(0,8))
        
        dlg.bind('<Return>', lambda e: _ok())
        dlg.bind('<Escape>', lambda e: dlg.destroy())

    def _show_filter_help(self):
        help_text = """Filter Rules Help:

1. Rule Types:
   • Extension (ext): Matches file extensions (e.g., 'jpg', 'txt').
   • Name (name): Matches file or folder names (e.g., 'node_modules', 'backup').
   • Full Path (path): Matches the full path (e.g., 'C:\\Data\\Temp\\*').

2. Wildcards:
   • *: Matches any number of characters.
   • ?: Matches a single character.
   • [abc]: Matches any one of the characters in brackets.

3. Precedence:
   • Include rules are checked first. If a file matches an include rule, it is backed up.
   • Exclude rules are checked next. If a file matches an exclude rule, it is skipped.
   • If no rules match, the default policy (Hidden/System attributes) applies.
"""
        messagebox.showinfo("Filter Help", help_text, parent=self)

    def _save(self):
        self.result = {'include': self.inc, 'exclude': self.exc}
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()

class SelectSourcesDialog(tk.Toplevel):
    def __init__(self, master, is_hidden_fn=None, title="Select Sources"):
        super().__init__(master)
        self.title(title)
        try:
            self.iconbitmap(resource_path('./icon/ezbak_title.ico'))
        except Exception:
            try: self.iconbitmap(resource_path('./icon/ezbak.ico'))
            except Exception: pass
        self.configure(bg="#2D3250"); self.geometry("640x480"); self.transient(master)
        try: self.grab_set()
        except Exception: pass
        self.is_hidden_fn = is_hidden_fn or (lambda p: False)
        self.selected_paths = []
        tk.Label(self, text="Select folders and files to back up.", bg="#2D3250", fg="white", font=("Arial", 11, "bold")).pack(anchor='w', padx=10, pady=(10, 5))
        top_controls = tk.Frame(self, bg="#2D3250"); top_controls.pack(fill="x", padx=10, pady=(0, 5))
        tk.Button(top_controls, text="Add Root Folder...", command=self._choose_root, bg="#7D98A1", fg="white", relief="flat").pack(side="left")
        tree_frame = tk.Frame(self, bg="#2D3250"); tree_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree = ttk.Treeview(tree_frame, columns=("fullpath",), displaycolumns=()); vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set); vsb.pack(side="right", fill="y"); self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewOpen>>", self._on_open); self.tree.bind("<Button-1>", self._on_click)
        self._checked = set(); self._item_path = {}
        self._add_drive_roots()
        action_frame = tk.Frame(self, bg="#2D3250"); action_frame.pack(fill="x", padx=10, pady=(5, 10))
        tk.Button(action_frame, text="OK", width=10, command=self._on_ok, bg="#336BFF", fg="white", relief="flat").pack(side="right")
        tk.Button(action_frame, text="Cancel", width=10, command=self._on_cancel, bg="#FF5733", fg="white", relief="flat").pack(side="right", padx=(0, 8))
    def _format(self, name, checked): return f"[{'x' if checked else ' '}] {name}"
    def _add_drive_roots(self):
        for code in range(ord('C'), ord('Z') + 1):
            drive = f"{chr(code)}:\\"
            if os.path.exists(drive):
                item = self.tree.insert("", "end", text=self._format(drive, False), open=False)
                self._item_path[item] = drive; self.tree.insert(item, "end", text="...")
    def _choose_root(self):
        path = filedialog.askdirectory(title="Select Root Folder")
        if path:
            item = self.tree.insert("", "end", text=self._format(path, False), open=False)
            self._item_path[item] = path; self.tree.insert(item, "end", text="...")
    def _on_open(self, event):
        item = self.tree.focus()
        if not item: return
        children = self.tree.get_children(item)
        if len(children) == 1 and self.tree.item(children[0], "text") == "...":
            self.tree.delete(children[0])
            path = self._item_path.get(item)
            # Check if the parent item is checked to propagate the state to new children.
            parent_is_checked = self.tree.item(item, "text").startswith("[x]")
            if not path: return
            try:
                entries = []
                with os.scandir(path) as it:
                    for entry in it:
                        if self.is_hidden_fn(entry.path): continue
                        is_dir = entry.is_dir(follow_symlinks=False)
                        entries.append((entry.name, is_dir, entry.path))
                for name, is_dir, full in sorted(entries, key=lambda t: (not t[1], t[0].lower())):
                    # Inherit the checked state from the parent when creating the child item.
                    child = self.tree.insert(item, "end", text=self._format(name, parent_is_checked), open=False)
                    self._item_path[child] = full
                    # If the parent is checked, the new child must also be added to the checked set.
                    if parent_is_checked:
                        self._checked.add(child)
                    if is_dir: self.tree.insert(child, "end", text="...")
            except Exception: pass
    def _toggle_item(self, item):
        text = self.tree.item(item, "text")
        if not text: return
        new_checked = not text.startswith("[x]")
        name = text[4:] if len(text) >= 4 else text
        self.tree.item(item, text=self._format(name, new_checked))
        if new_checked: self._checked.add(item)
        else: self._checked.discard(item)
        # Propagate to descendants
        for child in self.tree.get_children(item):
            if self.tree.item(child, "text") == "...":
                continue
            self._apply_to_descendants(child, new_checked)

    def _apply_to_descendants(self, item, checked):
        """Recursively apply the checked state to an item and all its descendants."""
        text = self.tree.item(item, "text")
        name = text[4:] if len(text) >= 4 else text
        self.tree.item(item, text=self._format(name, checked))
        if checked: self._checked.add(item)
        else: self._checked.discard(item)
        for child in self.tree.get_children(item):
            if self.tree.item(child, "text") == "...":
                continue
            self._apply_to_descendants(child, checked)
    def _on_click(self, event):
        item = self.tree.identify_row(event.y)
        if item and "text" in str(self.tree.identify("element", event.x, event.y)).lower(): self._toggle_item(item)
    def _on_ok(self):
        paths = []
        for item in list(self._checked):
            p = self._item_path.get(item)
            if not p: continue
            parent = self.tree.parent(item); is_top_level = True
            while parent:
                if parent in self._checked: is_top_level = False; break
                parent = self.tree.parent(parent)
            if is_top_level: paths.append(p)
        self.selected_paths = paths; self.grab_release(); self.destroy()
    def _on_cancel(self): self.selected_paths = []; self.grab_release(); self.destroy()

class MountVolDialog(tk.Toplevel):
    """Volume GUID만 선택하는 단순화된 다이얼로그"""
    def __init__(self, master, title="Select Volume"):
        super().__init__(master)
        self.title(title)
        try:
            self.iconbitmap(resource_path('./icon/ezbak_title.ico'))
        except Exception:
            try: self.iconbitmap(resource_path('./icon/ezbak.ico'))
            except Exception: pass
        self.configure(bg="#2D3250"); self.geometry("680x400"); self.transient(master)
        try: self.grab_set()
        except Exception: pass

        self.result = None

        main_frame = tk.Frame(self, bg="#2D3250", padx=10, pady=10)
        main_frame.pack(fill="both", expand=True)

        tk.Label(main_frame, text="Select a volume for backup:",
                 bg="#2D3250", fg="white", font=("Arial", 10, "bold")).pack(anchor='w', pady=(0, 5))

        info_label = tk.Label(main_frame,
                              text="The volume will be temporarily mounted during backup and unmounted after completion.",
                              bg="#2D3250", fg="#FFD700", font=("Arial", 9), wraplength=650, justify="left")
        info_label.pack(anchor='w', pady=(0, 10))

        tree_frame = tk.Frame(main_frame)
        tree_frame.pack(fill="both", expand=True, pady=5)

        self.tree = ttk.Treeview(tree_frame, columns=("guid", "size"), show="headings", selectmode="browse")
        self.tree.heading("guid", text="Volume GUID")
        self.tree.heading("size", text="Capacity")
        self.tree.column("guid", width=480)
        self.tree.column("size", width=150, anchor='e')

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        action_frame = tk.Frame(main_frame, bg="#2D3250")
        action_frame.pack(fill="x", pady=(10, 0))
        tk.Button(action_frame, text="OK", width=10, command=self._on_ok,
                  bg="#336BFF", fg="white", relief="flat").pack(side="right")
        tk.Button(action_frame, text="Cancel", width=10, command=self._on_cancel,
                  bg="#FF5733", fg="white", relief="flat").pack(side="right", padx=(0, 8))

        self._populate_volumes()

    def _populate_volumes(self):
        self.tree.delete(*self.tree.get_children())
        ps_failed = False

        # --- 방법 1: PowerShell 시도 ---
        try:
            ps_script = """
            Get-Volume | ForEach-Object {
                [PSCustomObject]@{
                    Guid = $_.Path;
                    Capacity = $_.Size;
                }
            } | ConvertTo-Json -Compress
            """
            cmd = ['powershell', '-NoProfile', '-Command', ps_script]
            ps_env = os.environ.copy()
            ps_env['LC_ALL'] = 'C'
            output = subprocess.check_output(cmd, shell=True, env=ps_env,
                                             stderr=subprocess.PIPE, timeout=10)
            json_output = output.decode('utf-8', errors='ignore').strip()
            volumes_data = []

            if json_output:
                if json_output.startswith('['):
                    volumes_data = json.loads(json_output)
                else:
                    volumes_data = [json.loads(json_output)]

            for vol in volumes_data:
                try:
                    capacity_bytes = int(vol.get('Capacity', 0))
                    guid = vol.get('Guid', '').strip()
                    if capacity_bytes > (1 * 1024 * 1024 * 1024) and guid:
                        if not guid.endswith('\\'): guid += '\\'
                        display_size = format_bytes(capacity_bytes)
                        self.tree.insert("", "end", values=(guid, display_size))
                except (ValueError, TypeError):
                    continue

            # PowerShell로 볼륨을 찾았으면 성공
            if self.tree.get_children():
                return

        except Exception as ps_error:
            ps_failed = True
            print(f"PowerShell failed: {ps_error}")  # 디버깅용

        # --- 방법 2: mountvol fallback ---
        try:
            env = os.environ.copy()
            env['LC_ALL'] = 'C'
            output = subprocess.check_output("mountvol", text=True, encoding='utf-8',
                                             errors='ignore', shell=True, env=env)

            volumes = {}
            current_guid = None
            guid_pattern = re.compile(r"(\\\\\?\\Volume\{[a-fA-F0-9-]+\}\\)")

            for line in output.splitlines():
                match = guid_pattern.search(line)
                if match:
                    current_guid = match.group(1)
                    if current_guid not in volumes:
                        volumes[current_guid] = []
                elif current_guid:
                    if line.startswith('    ') and line.strip():
                        volumes[current_guid].append(line.strip())
                    else:
                        current_guid = None

            for guid in sorted(volumes.keys()):
                display_size = "N/A"
                total_bytes = 0

                try:
                    usage = shutil.disk_usage(guid)
                    total_bytes = usage.total
                    display_size = format_bytes(total_bytes)
                except Exception:
                    pass

                # 1GB 이상이거나 크기를 알 수 없는 경우 표시
                if total_bytes > (1 * 1024 * 1024 * 1024) or display_size == "N/A":
                    self.tree.insert("", "end", values=(guid, display_size))

            # 여전히 볼륨이 없으면 에러 표시
            if not self.tree.get_children():
                messagebox.showinfo("No Volumes Found",
                                    "Could not find any mountable volumes on this system.",
                                    parent=self)

        except Exception as mountvol_error:
            messagebox.showerror("Error",
                                 f"Failed to list volumes.\n\nPowerShell: {'Failed' if ps_failed else 'No volumes'}\n"
                                 f"mountvol: {mountvol_error}",
                                 parent=self)

    def _on_ok(self):
        selected_item = self.tree.focus()
        if not selected_item:
            messagebox.showwarning("Warning", "Please select a volume.", parent=self)
            return

        values = self.tree.item(selected_item, 'values')
        guid = values[0]

        # GUID만 저장
        self.result = {'guid': guid}
        self.grab_release()
        self.destroy()

    def _on_cancel(self):
        self.grab_release()
        self.destroy()

class ScheduleBackupDialog(tk.Toplevel):
    def __init__(self, master, initial_data=None):
        super().__init__(master)
        self.is_edit_mode = initial_data is not None
        self.title("Edit Schedule" if self.is_edit_mode else "Schedule Backup")
        try:
            self.iconbitmap(resource_path('./icon/ezbak_title.ico'))
        except (tk.TclError, FileNotFoundError):
            try: self.iconbitmap(resource_path('./icon/ezbak.ico'))
            except tk.TclError: pass
        self.configure(bg="#2D3250"); self.geometry("560x620"); self.transient(master)
        try: self.grab_set()
        except Exception: pass
        self.action = None; self.result = None

        # --- Set defaults or load from initial_data ---
        data = initial_data or {}
        users = list(master.user_combo['values']) if getattr(master, 'user_combo', None) else []
        default_user = master.user_var.get() if getattr(master, 'user_var', None) and master.user_var.get() else (users[0] if users else "")

        task_name = data.get('task_name', f"ezBAK_Backup_{default_user}" if default_user else "ezBAK_Backup")
        backup_type = data.get('type', 'user_profile')
        user = data.get('user', default_user)
        self.sources = data.get('sources', [])
        dest = data.get('dest', "")
        mount_info = data.get('mount_info')
        schedule = data.get('schedule', 'Daily')
        time_str = data.get('time_str', '02:00')
        if self.is_edit_mode:
            days_values = {k: (k in data.get('days', [])) for k in ['MON','TUE','WED','THU','FRI','SAT','SUN']}
        else:
            days_values = {k: (k == 'MON') for k in ['MON','TUE','WED','THU','FRI','SAT','SUN']}
        include_hidden = data.get('include_hidden', False)
        include_system = data.get('include_system', False)
        retention_count = str(data.get('retention_count', '2'))
        log_retention_days = str(data.get('log_retention_days', '30'))
        email_config = data.get('email_notification', {})
        ftp_config = data.get('ftp_transfer', {})
        direct_ftp = data.get('direct_ftp', False)
        
        # Load filters
        fobj = data.get('filters', {})
        inc = fobj.get('include', []) if isinstance(fobj, dict) else []
        exc = fobj.get('exclude', []) if isinstance(fobj, dict) else []
        self.filters = {'include': inc, 'exclude': exc}
        self.previous_user = user

        # --- Notebook (Tabs) ---
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)

        # Tab 1: General
        self.general_tab = tk.Frame(self.notebook, bg="#2D3250")
        self.notebook.add(self.general_tab, text="General")
        
        # Tab 2: Email
        self.email_tab = tk.Frame(self.notebook, bg="#2D3250")
        self.notebook.add(self.email_tab, text="Email")

        # Tab 3: FTP
        self.ftp_tab = tk.Frame(self.notebook, bg="#2D3250")
        self.notebook.add(self.ftp_tab, text="FTP")

        # --- General Tab Content ---
        frm = self.general_tab # Use general_tab as the main frame for existing logic
        # Grid config for general tab
        frm.columnconfigure(1, weight=1)

        row = 0
        def add_label(text, parent=frm): nonlocal row; tk.Label(parent, text=text, bg="#2D3250", fg="white", font=("Arial", 10, "bold")).grid(row=row, column=0, sticky='w', pady=4, padx=5)
        def add_entry(var, width=34, parent=frm): nonlocal row; e = tk.Entry(parent, textvariable=var, width=width); e.grid(row=row, column=1, sticky='w', pady=4, padx=5); row += 1; return e

        add_label("Task Name"); self.task_name_var = tk.StringVar(value=task_name); add_entry(self.task_name_var)

        add_label("Backup Type")
        self.backup_type_var = tk.StringVar(value=backup_type)
        type_frame = tk.Frame(frm, bg="#2D3250")
        type_frame.grid(row=row, column=1, columnspan=2, sticky='w', pady=4)
        # Use tk.Radiobutton for better styling and consistency
        tk.Radiobutton(type_frame, text="User Profile", variable=self.backup_type_var, value='user_profile', command=self._toggle_backup_type, bg="#2D3250", fg="white", selectcolor="#2D3250", activebackground="#2D3250", activeforeground="white", bd=0, font=("Arial", 10)).pack(side='left', padx=(0, 10))
        tk.Radiobutton(type_frame, text="Custom Selection", variable=self.backup_type_var, value='custom_copy', command=self._toggle_backup_type, bg="#2D3250", fg="white", selectcolor="#2D3250", activebackground="#2D3250", activeforeground="white", bd=0, font=("Arial", 10)).pack(side='left', padx=(0, 10))
        tk.Radiobutton(type_frame, text="Data Sync", variable=self.backup_type_var, value='data_sync', command=self._toggle_backup_type, bg="#2D3250", fg="white", selectcolor="#2D3250", activebackground="#2D3250", activeforeground="white", bd=0, font=("Arial", 10)).pack(side='left')
        row += 1

        # --- User Profile Widgets (placed directly in main grid for alignment) ---
        self.user_label = tk.Label(frm, text="User", bg="#2D3250", fg="white", font=("Arial", 10, "bold"))
        self.user_var2 = tk.StringVar(value=user)
        self.user_combo2 = ttk.Combobox(frm, textvariable=self.user_var2, values=users, state='readonly', width=32)
        self.user_combo2.bind('<<ComboboxSelected>>', self._on_user_change)

        # --- Custom Selection Widgets (placed directly in main grid for alignment) ---
        self.custom_label = tk.Label(frm, text="Backup Sources", bg="#2D3250", fg="white", font=("Arial", 10, "bold"))
        self.custom_source_frame = tk.Frame(frm, bg="#2D3250")
        self.source_listbox = tk.Listbox(self.custom_source_frame, height=5, width=34)
        self.source_listbox.pack(side='left', fill='both', expand=True)
        for path in self.sources: self.source_listbox.insert(tk.END, path)
        tk.Button(self.custom_source_frame, text="Select...", command=self._select_sources, bg="#7D98A1", fg="white", relief="flat").pack(side='left', padx=(6,0), anchor='n')

        # Grid all toggleable widgets to the same row, their visibility will be managed by _toggle_backup_type
        self.user_label.grid(row=row, column=0, sticky='w', pady=4)
        self.user_combo2.grid(row=row, column=1, sticky='w', pady=4)
        self.custom_label.grid(row=row, column=0, sticky='w', pady=4)
        self.custom_source_frame.grid(row=row, column=1, sticky='nsew', pady=4)
        row += 1

        self.dest_label = tk.Label(frm, text="Destination Folder", bg="#2D3250", fg="white", font=("Arial", 10, "bold"))
        self.dest_label.grid(row=row, column=0, sticky='w', pady=4)
        self.dest_var = tk.StringVar(value=dest)
        dest_frame = tk.Frame(frm, bg="#2D3250")
        dest_frame.grid(row=row, column=1, columnspan=2, sticky='w', pady=4)
        self.dest_entry = tk.Entry(dest_frame, textvariable=self.dest_var, width=28)
        self.dest_entry.pack(side='left')
        self.browse_dest_btn = tk.Button(dest_frame, text="Browse...", command=self._browse_dest, bg="#7D98A1", fg="white", relief="flat")
        self.browse_dest_btn.pack(side='left', padx=6); row += 1

        add_label("Mount Options")
        self.use_mountvol_var = tk.BooleanVar(value=(mount_info is not None))
        self.mountvol_chk = tk.Checkbutton(frm, text="Use Temporary Mount", variable=self.use_mountvol_var, command=self._toggle_dest_browse, bg="#2D3250", fg="white", selectcolor="#2D3250", activebackground="#2D3250", activeforeground="white", bd=0, font=("Arial", 10))
        self.mountvol_chk.grid(row=row, column=1, sticky='w', pady=4)
        row += 1

        self.direct_ftp_var = tk.BooleanVar(value=direct_ftp)
        self.direct_ftp_chk = tk.Checkbutton(frm, text="Direct FTP-Transfer (No Local Backup)", variable=self.direct_ftp_var, command=self._toggle_direct_ftp, bg="#2D3250", fg="white", selectcolor="#2D3250", activebackground="#2D3250", activeforeground="white", bd=0, font=("Arial", 10))
        self.direct_ftp_chk.grid(row=row, column=1, sticky='w', pady=4)
        row += 1

        add_label("Schedule"); self.schedule_var = tk.StringVar(value=schedule); schedule_values = ['Daily', 'Weekly'] + [str(i) for i in range(1, 32)]
        self.schedule_combo = ttk.Combobox(frm, textvariable=self.schedule_var, values=schedule_values, state='readonly', width=12); self.schedule_combo.grid(row=row, column=1, sticky='w', pady=4)
        self.schedule_combo.bind('<<ComboboxSelected>>', self._toggle_weekly); row += 1

        add_label("Time (HH:MM)")
        try:
            init_h, init_m = time_str.split(':')
        except ValueError:
            init_h, init_m = "02", "00"

        self.hour_var = tk.StringVar(value=init_h)
        self.minute_var = tk.StringVar(value=init_m)
        
        time_frame = tk.Frame(frm, bg="#2D3250")
        time_frame.grid(row=row, column=1, sticky='w', pady=4)
        
        hours = [f"{h:02d}" for h in range(24)]
        minutes = [f"{m:02d}" for m in range(60)]
        
        self.hour_combo = ttk.Combobox(time_frame, textvariable=self.hour_var, values=hours, width=5, state='readonly')
        self.hour_combo.pack(side='left')
        
        tk.Label(time_frame, text=":", bg="#2D3250", fg="white", font=("Arial", 10, "bold")).pack(side='left', padx=2)
        
        self.minute_combo = ttk.Combobox(time_frame, textvariable=self.minute_var, values=minutes, width=5, state='readonly')
        self.minute_combo.pack(side='left')
        
        row += 1

        self.days_vars = {k: tk.BooleanVar(value=v) for k, v in days_values.items()}
        self.days_frame = tk.Frame(frm, bg="#2D3250"); tk.Label(self.days_frame, text="Days:", bg="#2D3250", fg="white").pack(side='left', padx=(0,6))
        for k in ['MON','TUE','WED','THU','FRI','SAT','SUN']: tk.Checkbutton(self.days_frame, text=k, variable=self.days_vars[k], bg="#2D3250", fg="white", selectcolor="#2D3250").pack(side='left')
        self.days_frame.grid(row=row, column=1, sticky='w', pady=4); row += 1

        self.inc_hidden_var = tk.BooleanVar(value=include_hidden); self.inc_system_var = tk.BooleanVar(value=include_system)
        tk.Checkbutton(frm, text="Include Hidden", variable=self.inc_hidden_var, bg="#2D3250", fg="white", selectcolor="#2D3250").grid(row=row, column=1, sticky='w', pady=4); row += 1
        tk.Checkbutton(frm, text="Include System", variable=self.inc_system_var, bg="#2D3250", fg="white", selectcolor="#2D3250").grid(row=row, column=1, sticky='w', pady=2); row += 1

        add_label("Filters")
        tk.Button(frm, text="Manage Filters...", command=self._open_filter_manager, bg="#7D98A1", fg="white", relief="flat").grid(row=row, column=1, sticky='w', pady=4); row += 1

        self.retention_label = tk.Label(frm, text="Backups to Keep", bg="#2D3250", fg="white", font=("Arial", 10, "bold"))
        self.retention_label.grid(row=row, column=0, sticky='w', pady=2)
        retention_frame = tk.Frame(frm, bg="#2D3250"); retention_frame.grid(row=row, column=1, columnspan=2, sticky='w', pady=2)
        self.retention_var = tk.StringVar(value=retention_count)
        self.retention_spinbox = tk.Spinbox(retention_frame, from_=0, to=99, textvariable=self.retention_var, width=5)
        self.retention_spinbox.pack(side='left')
        self.retention_note = tk.Label(retention_frame, text="(0 = keep all)", bg="#2D3250", fg="gray")
        self.retention_note.pack(side='left', padx=10)
        row += 1

        add_label("Logs to Keep"); log_retention_frame = tk.Frame(frm, bg="#2D3250"); log_retention_frame.grid(row=row, column=1, columnspan=2, sticky='w', pady=2)
        self.log_retention_days_var = tk.StringVar(value=log_retention_days)
        tk.Spinbox(log_retention_frame, from_=0, to=365, textvariable=self.log_retention_days_var, width=5).pack(side='left')
        tk.Label(log_retention_frame, text="days (0 = keep all)", bg="#2D3250", fg="gray").pack(side='left', padx=10); row += 1
        
        # --- Email Section removed from General Tab ---
        # (Moved to Email Tab)
        # --- Email Tab Content ---
        email_frm = self.email_tab
        
        self.email_enabled_var = tk.BooleanVar(value=email_config.get('enabled', False))
        email_chk = tk.Checkbutton(email_frm, text="Enable Email Notification", variable=self.email_enabled_var, command=self._toggle_email_fields, bg="#2D3250", fg="white", selectcolor="#2D3250", activebackground="#2D3250", activeforeground="white", bd=0, font=("Arial", 10, "bold"))
        email_chk.pack(anchor='w', padx=10, pady=10)

        self.email_fields_frame = tk.Frame(email_frm, bg="#2D3250")
        self.email_fields_frame.pack(fill='x', padx=10)

        email_row = 0
        def add_email_label(text):
            nonlocal email_row
            tk.Label(self.email_fields_frame, text=text, bg="#2D3250", fg="white").grid(row=email_row, column=0, sticky='w', pady=2, padx=5)
        def add_email_entry(var, width=38, show=None):
            nonlocal email_row
            e = tk.Entry(self.email_fields_frame, textvariable=var, width=width, show=show)
            e.grid(row=email_row, column=1, sticky='w', pady=2, padx=5)
            email_row += 1
            return e

        add_email_label("SMTP Server:"); self.smtp_server_var = tk.StringVar(value=email_config.get('server', 'smtp.gmail.com')); add_email_entry(self.smtp_server_var)
        add_email_label("Port:"); self.smtp_port_var = tk.StringVar(value=email_config.get('port', '587')); add_email_entry(self.smtp_port_var, width=10)
        add_email_label("Sender Email:"); self.smtp_sender_var = tk.StringVar(value=email_config.get('sender', '')); add_email_entry(self.smtp_sender_var)
        add_email_label("Recipient Email:"); self.smtp_recipient_var = tk.StringVar(value=email_config.get('recipient', '')); add_email_entry(self.smtp_recipient_var)
        add_email_label("Username:"); self.smtp_user_var = tk.StringVar(value=email_config.get('user', '')); add_email_entry(self.smtp_user_var)
        add_email_label("Password:"); self.smtp_password_var = tk.StringVar(value=_decrypt_password(email_config.get('password', ''))); add_email_entry(self.smtp_password_var, show='*')
        
        self.notify_success_var = tk.BooleanVar(value=email_config.get('notify_on_success', False))
        tk.Checkbutton(self.email_fields_frame, text="Notify on Success", variable=self.notify_success_var, bg="#2D3250", fg="white", selectcolor="#2D3250", activebackground="#2D3250", activeforeground="white", bd=0).grid(row=email_row, column=0, columnspan=2, sticky='w', pady=5, padx=5)
        email_row += 1
        
        self.notify_failure_var = tk.BooleanVar(value=email_config.get('notify_on_failure', True))
        tk.Checkbutton(self.email_fields_frame, text="Notify on Failure", variable=self.notify_failure_var, bg="#2D3250", fg="white", selectcolor="#2D3250", activebackground="#2D3250", activeforeground="white", bd=0).grid(row=email_row, column=0, columnspan=2, sticky='w', pady=5, padx=5)


        # --- FTP Tab Content ---
        ftp_frm = self.ftp_tab
        
        self.ftp_enabled_var = tk.BooleanVar(value=ftp_config.get('enabled', False))
        ftp_chk = tk.Checkbutton(ftp_frm, text="Enable FTP Transfer", variable=self.ftp_enabled_var, command=self._toggle_ftp_fields, bg="#2D3250", fg="white", selectcolor="#2D3250", activebackground="#2D3250", activeforeground="white", bd=0, font=("Arial", 10, "bold"))
        ftp_chk.pack(anchor='w', padx=10, pady=10)

        self.ftp_fields_frame = tk.Frame(ftp_frm, bg="#2D3250")
        self.ftp_fields_frame.pack(fill='x', padx=10)

        ftp_row = 0
        def add_ftp_label(text):
            nonlocal ftp_row
            tk.Label(self.ftp_fields_frame, text=text, bg="#2D3250", fg="white").grid(row=ftp_row, column=0, sticky='w', pady=2, padx=5)
        def add_ftp_entry(var, width=38, show=None):
            nonlocal ftp_row
            e = tk.Entry(self.ftp_fields_frame, textvariable=var, width=width, show=show)
            e.grid(row=ftp_row, column=1, sticky='w', pady=2, padx=5)
            ftp_row += 1
            return e

        add_ftp_label("FTP Host:"); self.ftp_host_var = tk.StringVar(value=ftp_config.get('host', '')); add_ftp_entry(self.ftp_host_var)
        add_ftp_label("Port:"); self.ftp_port_var = tk.StringVar(value=ftp_config.get('port', '21')); add_ftp_entry(self.ftp_port_var, width=10)
        add_ftp_label("Username:"); self.ftp_user_var = tk.StringVar(value=ftp_config.get('user', '')); add_ftp_entry(self.ftp_user_var)
        add_ftp_label("Password:"); self.ftp_password_var = tk.StringVar(value=_decrypt_password(ftp_config.get('password', ''))); add_ftp_entry(self.ftp_password_var, show='*')
        add_ftp_label("Remote Path:"); self.ftp_remote_path_var = tk.StringVar(value=ftp_config.get('remote_path', '/')); add_ftp_entry(self.ftp_remote_path_var)

        # Adjust dialog geometry
        self.geometry("600x650")

        # --- Buttons ---
        btns = tk.Frame(self, bg="#2D3250"); btns.pack(fill='x', padx=12, pady=(6,12))
        create_button_text = "Save" if self.is_edit_mode else "Create"
        tk.Button(btns, text=create_button_text, command=self._create, bg="#336BFF", fg="white", relief="flat", width=12).pack(side='right')
        if self.is_edit_mode:
            tk.Button(btns, text="Delete", command=self._delete, bg="#FF5733", fg="white", relief="flat", width=12).pack(side='right', padx=(0,8))
        tk.Button(btns, text="Close", command=self._close, bg="#7D98A1", fg="white", relief="flat", width=10).pack(side='right', padx=(0,8))
        self._toggle_weekly(); self._toggle_backup_type(); self._toggle_dest_browse(); self._toggle_email_fields(); self._toggle_ftp_fields(); self._toggle_direct_ftp()

    def _toggle_direct_ftp(self):
        is_direct = self.direct_ftp_var.get()
        if is_direct:
            self.dest_entry.config(state='disabled')
            self.browse_dest_btn.config(state='disabled')
            self.mountvol_chk.config(state='disabled')
            self.dest_label.config(fg="gray")
        else:
            self._toggle_dest_browse() # Restore state based on mountvol
            self.mountvol_chk.config(state='normal')
            self.dest_label.config(fg="white")

    def _toggle_ftp_fields(self):
        state = 'normal' if self.ftp_enabled_var.get() else 'disabled'
        for widget in self.ftp_fields_frame.winfo_children():
            if isinstance(widget, (tk.Entry, tk.Label)): widget.configure(state=state)

    def _toggle_backup_type(self):
        is_user_profile = self.backup_type_var.get() == 'user_profile'
        is_data_sync = self.backup_type_var.get() == 'data_sync'
        
        if is_user_profile:
            self.user_label.grid()
            self.user_combo2.grid()
            self.custom_label.grid_remove()
            self.custom_source_frame.grid_remove()
            self._on_user_change()
        else:
            self.user_label.grid_remove()
            self.user_combo2.grid_remove()
            self.custom_label.grid()
            self.custom_source_frame.grid()
            current_task_name = self.task_name_var.get()
            if current_task_name.startswith("ezBAK_Backup_"): 
                if is_data_sync:
                    self.task_name_var.set("ezBAK_Sync")
                else:
                    self.task_name_var.set("ezBAK_Custom_Backup")
        
        # Data Sync일 경우 Backups to Keep 비활성화
        if is_data_sync:
            self.retention_label.config(fg="gray")
            self.retention_spinbox.config(state='disabled')
            self.retention_note.config(fg="darkgray")
        else:
            self.retention_label.config(fg="white")
            self.retention_spinbox.config(state='normal')
            self.retention_note.config(fg="gray")

    def _on_user_change(self, event=None):
        if self.backup_type_var.get() != 'user_profile': return
        new_user = self.user_var2.get()
        current_task_name = self.task_name_var.get()
        expected_old_task_name = f"ezBAK_Backup_{self.previous_user}" if self.previous_user else "ezBAK_Backup"
        if new_user and (current_task_name == expected_old_task_name or current_task_name == "ezBAK_Custom_Backup"):
            self.task_name_var.set(f"ezBAK_Backup_{new_user}")
        self.previous_user = new_user

    def _select_sources(self):
        runner = HeadlessBackupRunner({'include_hidden': self.inc_hidden_var.get(), 'include_system': self.inc_system_var.get()})
        dlg = SelectSourcesDialog(self, is_hidden_fn=runner.is_hidden, title="Select Backup Sources")
        self.wait_window(dlg); self.sources = dlg.selected_paths
        self.source_listbox.delete(0, tk.END)
        for path in self.sources: self.source_listbox.insert(tk.END, path)

    def _browse_dest(self):
        path = filedialog.askdirectory(title="Select Destination Folder")
        if path: self.dest_var.set(path)

    def _toggle_dest_browse(self):
        if self.direct_ftp_var.get():
            return # Handled by _toggle_direct_ftp

        is_mountvol = self.use_mountvol_var.get()
        state = 'disabled' if is_mountvol else 'normal'
        self.dest_entry.config(state=state)
        self.browse_dest_btn.config(state=state)
        if is_mountvol:
            self.dest_label.config(text="Backup Drive (Root)")
            if not self.is_edit_mode or self.dest_var.get() == "":
                self.dest_var.set("(Volume selected on creation)")
        else:
            self.dest_label.config(text="Destination Folder")
            if self.dest_var.get() == "(Volume selected on creation)":
                self.dest_var.set("")

    def _toggle_weekly(self, event=None):
        if self.schedule_var.get().lower() == 'weekly': self.days_frame.grid()
        else: self.days_frame.grid_remove()

    def _toggle_email_fields(self):
        state = 'normal' if self.email_enabled_var.get() else 'disabled'
        for widget in self.email_fields_frame.winfo_children():
            if isinstance(widget, (tk.Entry, tk.Label)): widget.configure(state=state)

    def _open_filter_manager(self):
        dlg = FilterManagerDialog(self, current_filters=self.filters)
        self.wait_window(dlg)
        if dlg.result:
            self.filters = dlg.result

    def _create(self):
        name = self.task_name_var.get().strip()
        # time_str = self.time_var.get().strip()
        time_str = f"{self.hour_var.get().strip()}:{self.minute_var.get().strip()}"
        sched = self.schedule_var.get().strip()
        days = [k for k,v in self.days_vars.items() if v.get()] if sched.lower() == 'weekly' else []

        try:
            retention_count = int(self.retention_var.get())
            if not (0 <= retention_count <= 99): raise ValueError
        except (ValueError, TypeError):
            messagebox.showwarning("Warning", "Please enter a valid number for 'Backups to Keep' (0-99).", parent=self)
            return

        try:
            log_retention_days = int(self.log_retention_days_var.get())
            if not (0 <= log_retention_days <= 365): raise ValueError
        except (ValueError, TypeError):
            messagebox.showwarning("Warning", "Please enter a valid number for 'Logs to Keep' (0-365).", parent=self)
            return

        email_config = {
            'enabled': self.email_enabled_var.get(),
            'notify_on_success': self.notify_success_var.get(),
            'notify_on_failure': self.notify_failure_var.get(),
            'server': self.smtp_server_var.get().strip(),
            'port': self.smtp_port_var.get().strip(),
            'sender': self.smtp_sender_var.get().strip(),
            'recipient': self.smtp_recipient_var.get().strip(),
            'user': self.smtp_user_var.get().strip(),
            'password': _encrypt_password(self.smtp_password_var.get())
        }

        ftp_config = {
            'enabled': self.ftp_enabled_var.get(),
            'host': self.ftp_host_var.get().strip(),
            'port': self.ftp_port_var.get().strip(),
            'user': self.ftp_user_var.get().strip(),
            'password': _encrypt_password(self.ftp_password_var.get()),
            'remote_path': self.ftp_remote_path_var.get().strip()
        }

        if ftp_config['enabled']:
            if not ftp_config['host']:
                messagebox.showwarning("Warning", "FTP Host is required when FTP Transfer is enabled.", parent=self)
                return

        if self.direct_ftp_var.get():
            if not ftp_config['enabled']:
                messagebox.showwarning("Warning", "FTP Transfer must be enabled when using Direct FTP-Transfer.", parent=self)
                return
            if not ftp_config['host']:
                messagebox.showwarning("Warning", "FTP Host is required for Direct FTP-Transfer.", parent=self)
                return

        backup_type = self.backup_type_var.get()
        user = None
        sources = []
        dest = self.dest_var.get().strip()
        mount_info = None

        if self.use_mountvol_var.get() and not self.direct_ftp_var.get():
            mount_dlg = MountVolDialog(self, title="Select Volume for Backup")
            self.wait_window(mount_dlg)
            if not getattr(mount_dlg, 'result', None):
                messagebox.showwarning("Warning", "Temporary mount selection is required.", parent=self)
                return
            mount_info = mount_dlg.result
            dest = mount_info['guid']
        else:
            if self.direct_ftp_var.get():
                dest = "DIRECT_FTP_TEMP" # Placeholder
            elif not dest:
                messagebox.showwarning("Warning", "Destination Folder is required.", parent=self)
                return

        if backup_type == 'user_profile':
            user = self.user_var2.get().strip()
            if not (user and dest and name and time_str and sched):
                messagebox.showwarning("Warning", "Please complete all fields.", parent=self)
                return
            user_profile_path = os.path.join("C:", os.sep, "Users", user)
            if not os.path.exists(user_profile_path):
                messagebox.showerror("Error", f"User folder for '{user}' not found.", parent=self)
                return

            # 스레드로 용량 계산
            self._start_size_calculation(user_profile_path, None, user, sources, dest, mount_info,
                                         name, time_str, sched, days, retention_count,
                                         log_retention_days, email_config, backup_type, self.filters, ftp_config, self.direct_ftp_var.get())

        elif backup_type == 'custom_copy':
            sources = self.sources
            if not (sources and dest and name and time_str and sched):
                messagebox.showwarning("Warning", "Please complete all fields.", parent=self)
                return

            # 스레드로 용량 계산
            self._start_size_calculation(None, sources, user, sources, dest, mount_info,
                                         name, time_str, sched, days, retention_count,
                                         log_retention_days, email_config, backup_type, self.filters, ftp_config, self.direct_ftp_var.get())

        elif backup_type == 'data_sync':
            sources = self.sources
            if not (sources and dest and name and time_str and sched):
                messagebox.showwarning("Warning", "Please complete all fields.", parent=self)
                return

            # 데이터 동기화는 용량 계산 없이 바로 스케줄 생성
            self._finalize_schedule_creation(None, sources, user, sources, dest, mount_info,
                                            name, time_str, sched, days, retention_count,
                                            log_retention_days, email_config, backup_type, self.filters, ftp_config, self.direct_ftp_var.get())

    def _start_size_calculation(self, user_profile_path, custom_sources, user, sources, dest,
                                mount_info, name, time_str, sched, days, retention_count,
                                log_retention_days, email_config, backup_type, filters, ftp_config, direct_ftp):
        """용량 계산을 별도 스레드로 실행"""

        # 진행 다이얼로그 생성
        progress_dlg = tk.Toplevel(self)
        progress_dlg.title("Calculating Size")
        progress_dlg.geometry("400x120")
        progress_dlg.configure(bg="#2D3250")
        progress_dlg.transient(self)
        progress_dlg.transient(self)
        try:
            progress_dlg.iconbitmap(resource_path('./icon/ezbak_title.ico'))
        except Exception:
            try: progress_dlg.iconbitmap(resource_path('./icon/ezbak.ico'))
            except Exception: pass
        progress_dlg.grab_set()

        # 창 중앙 배치
        progress_dlg.update_idletasks()
        x = (progress_dlg.winfo_screenwidth() // 2) - (400 // 2)
        y = (progress_dlg.winfo_screenheight() // 2) - (120 // 2)
        progress_dlg.geometry(f"400x120+{x}+{y}")

        tk.Label(progress_dlg, text="Calculating required disk space...",
                 bg="#2D3250", fg="white", font=("Arial", 11, "bold")).pack(pady=(20, 10))

        status_label = tk.Label(progress_dlg, text="Please wait...",
                                bg="#2D3250", fg="white", font=("Arial", 9))
        status_label.pack(pady=5)

        cancel_btn = tk.Button(progress_dlg, text="Cancel",
                               command=lambda: self._cancel_calculation(progress_dlg),
                               bg="#FF5733", fg="white", relief="flat", width=10)
        cancel_btn.pack(pady=10)

        # 취소 플래그
        self.calculation_cancelled = False

        # 스레드 시작
        thread = threading.Thread(
            target=self._calculate_size_worker,
            args=(user_profile_path, custom_sources, user, sources, dest, mount_info,
                  name, time_str, sched, days, retention_count, log_retention_days,
                  email_config, backup_type, filters, progress_dlg, status_label, ftp_config, direct_ftp),
            daemon=True
        )
        thread.start()

    def _cancel_calculation(self, progress_dlg):
        """용량 계산 취소"""
        self.calculation_cancelled = True
        try:
            progress_dlg.grab_release()
            progress_dlg.destroy()
        except:
            pass

    def _calculate_size_worker(self, user_profile_path, custom_sources, user, sources, dest,
                               mount_info, name, time_str, sched, days, retention_count,
                               log_retention_days, email_config, backup_type, filters, progress_dlg, status_label, ftp_config, direct_ftp):
        """백그라운드에서 용량 계산"""
        try:
            runner = HeadlessBackupRunner({
                'include_hidden': self.inc_hidden_var.get(),
                'include_system': self.inc_system_var.get(),
                'filters': filters
            })

            required_bytes = 0

            if user_profile_path:
                # 사용자 프로필 용량 계산
                self.after(0, lambda: status_label.config(text=f"Scanning user profile..."))
                required_bytes = runner.compute_total_bytes(user_profile_path)

            elif custom_sources:
                # 커스텀 소스 용량 계산
                total_sources = len(custom_sources)
                for idx, path in enumerate(custom_sources, 1):
                    if self.calculation_cancelled:
                        return

                    self.after(0, lambda i=idx, t=total_sources:
                    status_label.config(text=f"Scanning source {i}/{t}..."))

                    if os.path.isdir(path):
                        required_bytes += runner.compute_total_bytes(path)
                    elif os.path.isfile(path) and not runner.is_hidden(path):
                        try:
                            required_bytes += os.path.getsize(path)
                        except Exception:
                            pass

            if self.calculation_cancelled:
                return

            # UI 스레드에서 결과 처리
            self.after(0, lambda: self._handle_size_calculation_result(
                required_bytes, user, sources, dest, mount_info, name, time_str,
                sched, days, retention_count, log_retention_days, email_config,
                backup_type, filters, progress_dlg, ftp_config, direct_ftp
            ))

        except Exception as e:
            if not self.calculation_cancelled:
                self.after(0, lambda: self._handle_calculation_error(e, progress_dlg))

    def _handle_size_calculation_result(self, required_bytes, user, sources, dest, mount_info,
                                        name, time_str, sched, days, retention_count,
                                        log_retention_days, email_config, backup_type, filters, progress_dlg, ftp_config, direct_ftp):
        """용량 계산 완료 후 처리"""
        try:
            progress_dlg.grab_release()
            progress_dlg.destroy()
        except:
            pass

        # mountvol 사용 시 디스크 체크 건너뛰기
        if not mount_info and not direct_ftp:
            try:
                free_bytes = shutil.disk_usage(dest).free
            except FileNotFoundError:
                messagebox.showerror("Error", f"Destination folder '{dest}' not found.", parent=self)
                return
            except Exception as e:
                messagebox.showerror("Error", f"Could not check disk space: {e}", parent=self)
                return

            if required_bytes > free_bytes:
                msg = (f"Insufficient backup disk space.\n\n"
                       f"Required space: {format_bytes(required_bytes)}\n"
                       f"Available: {format_bytes(free_bytes)}\n\n"
                       f"Do you want to continue anyway?")
                if not messagebox.askyesno("Insufficient Space", msg, parent=self):
                    return

        # 스케줄 생성
        self.result = {
            'task_name': name,
            'schedule': sched,
            'time_str': time_str,
            'days': days,
            'type': backup_type,
            'user': user,
            'sources': sources,
            'dest': dest,
            'mount_info': mount_info,
            'retention_count': retention_count,
            'log_retention_days': log_retention_days,
            'include_hidden': self.inc_hidden_var.get(),
            'include_system': self.inc_system_var.get(),
            'email_notification': email_config,
            'ftp_transfer': ftp_config,
            'filters': self.filters,
            'direct_ftp': direct_ftp
        }
        self.action = 'create'
        self.grab_release()
        self.destroy()

    def _handle_calculation_error(self, error, progress_dlg):
        """용량 계산 중 에러 처리"""
        try:
            progress_dlg.grab_release()
            progress_dlg.destroy()
        except:
            pass

        messagebox.showerror("Error", f"Size calculation failed: {error}", parent=self)

    def _finalize_schedule_creation(self, user_profile_path, custom_sources, user, sources, dest,
                                    mount_info, name, time_str, sched, days, retention_count,
                                    log_retention_days, email_config, backup_type, filters, ftp_config, direct_ftp):
        """용량 계산 없이 바로 스케줄 생성 (data_sync용)"""
        # mountvol 사용 시 볼륨 선택
        if mount_info is None and self.use_mountvol_var.get() and not direct_ftp:
            mount_dlg = MountVolDialog(self, title="Select Volume for Backup")
            self.wait_window(mount_dlg)
            if not getattr(mount_dlg, 'result', None):
                messagebox.showwarning("Warning", "Temporary mount selection is required.", parent=self)
                return
            mount_info = mount_dlg.result
            dest = mount_info['guid']
        
        # 스케줄 생성
        self.result = {
            'task_name': name,
            'schedule': sched,
            'time_str': time_str,
            'days': days,
            'include_hidden': self.inc_hidden_var.get(),
            'include_system': self.inc_system_var.get(),
            'retention_count': retention_count,
            'log_retention_days': log_retention_days,
            'type': backup_type,
            'user': user,
            'sources': sources,
            'dest': dest,
            'mount_info': mount_info,
            'email_notification': email_config,
            'ftp_transfer': ftp_config,
            'filters': filters,
            'direct_ftp': direct_ftp
        }
        self.action = 'create'
        self.destroy()

    def _delete(self):
        self.task_name = self.task_name_var.get().strip()
        if not self.task_name: messagebox.showwarning("Warning", "Task Name is required to delete.", parent=self); return
        self.action = 'delete'; self.destroy()

    def _close(self): self.destroy()

class SchedulerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ezSBAK - Schedule Manager")
        try:
            # Try the title icon first (bundled with PyInstaller)
            self.iconbitmap(resource_path('./icon/ezbak_title.ico'))
        except tk.TclError:
            try:
                # Fallback to the regular icon
                self.iconbitmap(resource_path('./icon/ezbak.ico'))
            except tk.TclError:
                pass
        self.user_var = tk.StringVar(); users = self.load_users(); self.user_combo = {'values': users}
        if users: self.user_var.set(users[0])
        self.create_menu()
        self.create_widgets(); self.refresh_tasks()

    def create_menu(self):
        """메뉴바 생성"""
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        # Help 메뉴
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Visit Github", command=self.open_github)
    
    def open_github(self):
        """Github 페이지 열기"""
        webbrowser.open_new("https://github.com/gloriouslegacy/ezSBak/releases")

    def create_widgets(self):
        self.configure(bg="#2D3250"); self.geometry("950x400"); self.minsize(800, 300)
        style = ttk.Style(self); style.theme_use("clam")
        style.configure("Treeview", background="#424769", foreground="white", fieldbackground="#424769", rowheight=25)
        style.map('Treeview', background=[('selected', '#336BFF')])
        style.configure("Treeview.Heading", background="#7D98A1", foreground="white", font=("Arial", 10, "bold"), relief="flat")
        style.map("Treeview.Heading", relief=[('active','groove'),('pressed','sunken')])
        # Add style for the new LabelFrame
        style.configure("White.TLabelframe", background="#424769", bordercolor="white")
        style.configure("White.TLabelframe.Label", background="#424769", foreground="white")
        main_frame = tk.Frame(self, bg="#2D3250", padx=10, pady=10); main_frame.pack(fill="both", expand=True)
        tree_frame = tk.Frame(main_frame); tree_frame.pack(fill="both", expand=True, pady=(0, 10))
        self.task_tree = ttk.Treeview(tree_frame, columns=("name", "next_run", "status", "last_run_time", "last_run_result"), show="headings", selectmode="extended")
        self.task_tree.heading("name", text="Task Name"); self.task_tree.heading("next_run", text="Next Run Time"); self.task_tree.heading("status", text="Status")
        self.task_tree.heading("last_run_time", text="Last Run Time"); self.task_tree.heading("last_run_result", text="Last Run Result")
        self.task_tree.column("name", width=200, stretch=tk.YES)
        self.task_tree.column("next_run", width=150, stretch=tk.NO)
        self.task_tree.column("status", width=100, stretch=tk.NO)
        self.task_tree.column("last_run_time", width=150, stretch=tk.NO)
        self.task_tree.column("last_run_result", width=120, stretch=tk.NO)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.task_tree.yview); self.task_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y"); self.task_tree.pack(side="left", fill="both", expand=True)
        self.task_tree.tag_configure('failed', foreground='#FF6B6B') # Light red for failed tasks
        self.task_tree.bind("<Double-1>", self.open_edit_schedule_dialog)
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Run Now", command=self._run_task_now)
        self.context_menu.add_command(label="Stop", command=self._stop_task)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Disable", command=self._disable_task)
        self.context_menu.add_command(label="Enable", command=self._enable_task)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Open Latest Log", command=self._open_latest_log)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Delete", command=self.delete_selected_task)
        self.task_tree.bind("<Button-3>", self._show_context_menu)

        button_frame = tk.Frame(main_frame, bg="#2D3250"); button_frame.pack(fill="x")
        self.new_button = tk.Button(button_frame, text="New Schedule", command=self.open_new_schedule_dialog, bg="#2E7D32", fg="white", relief="flat", width=15, font=("Arial", 9, "bold"))
        self.new_button.pack(side="left", padx=(0, 5))
        self.delete_button = tk.Button(button_frame, text="Delete Selected", command=self.delete_selected_task, bg="#FF5733", fg="white", relief="flat", width=15, font=("Arial", 9, "bold"))
        self.delete_button.pack(side="left", padx=5)
        self.refresh_button = tk.Button(button_frame, text="Refresh", command=self.refresh_tasks, bg="#7D98A1", fg="white", relief="flat", width=12, font=("Arial", 9, "bold"))
        self.refresh_button.pack(side="left", padx=5)

        self.open_log_folder_button = tk.Button(button_frame, text="Open Log Folder", command=self.open_log_folder, bg="#FFA500", fg="white", relief="flat", width=15, font=("Arial", 9, "bold"))
        self.open_log_folder_button.pack(side="left", padx=5)

        self.task_scheduler_button = tk.Button(button_frame, text="Task Scheduler", command=self.open_task_scheduler, bg="#00796B", fg="white", relief="flat", width=15, font=("Arial", 9, "bold"))
        self.task_scheduler_button.pack(side="left", padx=5)

        self.disk_mgmt_button = tk.Button(button_frame, text="Disk Management", command=self.open_disk_management, bg="#5E35B1", fg="white", relief="flat", width=15, font=("Arial", 9, "bold"))
        self.disk_mgmt_button.pack(side="left", padx=5)

        self.close_button = tk.Button(button_frame, text="Close", command=self.destroy, bg="#455A64", fg="white", relief="flat", width=12, font=("Arial", 9, "bold"))
        self.close_button.pack(side="right")

        bottom_frame = tk.Frame(main_frame, bg="#2D3250"); bottom_frame.pack(fill="x", side="bottom", pady=(5, 0))
        self.status_label = tk.Label(bottom_frame, text="Ready.", bg="#2D3250", fg="white", anchor="w"); self.status_label.pack(side="left")

    def set_buttons_state(self, state):
        self.new_button.config(state=state); self.delete_button.config(state=state); self.refresh_button.config(state=state)
        self.open_log_folder_button.config(state=state)
        self.task_scheduler_button.config(state=state)
        self.disk_mgmt_button.config(state=state)

    def get_used_drive_letters(self):
        """Returns a set of used drive letters (uppercase, without colon)."""
        used = set()
        try:
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for i in range(26):
                if bitmask & (1 << i):
                    used.add(chr(65 + i))  # 'A'..'Z'
        except Exception:
            # Fallback probe
            for i in range(ord('A'), ord('Z') + 1):
                letter = chr(i)
                if os.path.exists(f"{letter}:\\"):
                    used.add(letter)
        return used
    def load_users(self):
        users_path = os.path.join("C:", os.sep, "Users")
        try: return [d for d in os.listdir(users_path) if os.path.isdir(os.path.join(users_path, d)) and not d.startswith('.') and d.lower() != 'all users']
        except Exception: return []

    def open_log_folder(self):
        """Opens the destination (log) folder for the selected task."""
        selected_item = self.task_tree.focus()
        if not selected_item:
            messagebox.showwarning("Warning", "Please select a task first.", parent=self)
            return
        try:
            task_name = self.task_tree.item(selected_item, 'values')[0]
            config_path = os.path.join(get_schedules_config_dir(), f"{task_name}.json")
            if not os.path.exists(config_path):
                messagebox.showerror("Error", f"Configuration file for '{task_name}' not found.", parent=self); return
            with open(config_path, 'r', encoding='utf-8') as f: config_data = json.load(f)
            dest_path = config_data.get('dest')
            if not dest_path: messagebox.showerror("Error", f"Destination folder is not defined for '{task_name}'.", parent=self); return
            os.startfile(dest_path)
            self.status_label.config(text=f"Opened log folder for '{task_name}'.")
        except (IndexError, KeyError): messagebox.showerror("Error", "Could not retrieve task name from selection.", parent=self)
        except Exception as e: messagebox.showerror("Error", f"Failed to open log folder:\n{e}", parent=self)

    def open_task_scheduler(self):
        """Opens the Windows Task Scheduler MMC snap-in."""
        try:
            os.startfile('taskschd.msc')
            self.status_label.config(text="Opening Windows Task Scheduler...")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open Task Scheduler:\n{e}", parent=self)

    def open_disk_management(self):
        """Opens the Windows Disk Management console."""
        try:
            subprocess.Popen(['diskmgmt.msc'], shell=True)
            self.status_label.config(text="Opening Disk Management...")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open Disk Management:\n{e}", parent=self)

    def _show_context_menu(self, event):
        """Display the context menu on right-click."""
        item = self.task_tree.identify_row(event.y)
        if item:
            # If the clicked item is not part of the current selection, clear the selection and select only that item.
            if item not in self.task_tree.selection():
                self.task_tree.selection_set(item)
            self.task_tree.focus(item)
            self.context_menu.post(event.x_root, event.y_root)

    def _open_latest_log(self):
        """Finds and opens the most recent log file for the selected task."""
        selected_item = self.task_tree.focus()
        if not selected_item: return

        try:
            task_name = self.task_tree.item(selected_item, 'values')[0]
        except (IndexError, KeyError):
            messagebox.showerror("Error", "Could not retrieve task name from selection.", parent=self)
            return

        try:
            config_path = os.path.join(get_schedules_config_dir(), f"{task_name}.json")
            if not os.path.exists(config_path):
                messagebox.showinfo("Info", f"No configuration file found for '{task_name}'. Cannot find logs.", parent=self)
                return

            with open(config_path, 'r', encoding='utf-8') as f: config_data = json.load(f)
            dest_path = config_data.get('dest')
            if not dest_path or not os.path.isdir(dest_path):
                messagebox.showinfo("Info", f"Destination folder for '{task_name}' not found or not configured.", parent=self)
                return

            runner = HeadlessBackupRunner(config_data)
            base_name = runner._get_base_name()
            log_prefix = f"{base_name}_backup_"

            log_files = [f for f in os.listdir(dest_path) if f.startswith(log_prefix) and f.endswith(".log") and os.path.isfile(os.path.join(dest_path, f))]
            if not log_files:
                messagebox.showinfo("Info", f"No log files found for task '{task_name}' in '{dest_path}'.", parent=self)
                return

            latest_log_path = os.path.join(dest_path, sorted(log_files, reverse=True)[0])
            os.startfile(latest_log_path)
            self.status_label.config(text=f"Opened latest log for '{task_name}'.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open log file:\n{e}", parent=self)

    def _run_task_now(self):
        """Runs all selected scheduled tasks immediately."""
        selected_items = self.task_tree.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "Please select one or more tasks to run.", parent=self)
            return

        task_names = [self.task_tree.item(item, 'values')[0] for item in selected_items if self.task_tree.item(item, 'values')]
        if not task_names:
            messagebox.showerror("Error", "Could not retrieve task names from selection.", parent=self)
            return

        if len(task_names) == 1:
            confirm_message = f"Are you sure you want to run the task '{task_names[0]}' now?"
        else:
            confirm_message = f"Are you sure you want to run {len(task_names)} selected tasks now?"

        if messagebox.askyesno("Confirm Run", confirm_message, parent=self):
            self.set_buttons_state("disabled")
            self.status_label.config(text=f"Attempting to run {len(task_names)} task(s)...")
            self.update_idletasks()
            threading.Thread(target=self._run_tasks_worker, args=(task_names,), daemon=True).start()

    def _run_tasks_worker(self, task_names):
        """Worker thread to execute schtasks /Run for multiple tasks."""
        success_count = 0; failed_tasks = []
        for task_name in task_names:
            try:
                cmd = ["schtasks", "/Run", "/TN", task_name]
                subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True, encoding='cp949', errors='ignore')
                success_count += 1
            except Exception:
                failed_tasks.append(task_name)
        self.after(0, self._on_run_tasks_finished, success_count, failed_tasks)

    def _on_run_tasks_finished(self, success_count, failed_tasks):
        """Callback to show results after running tasks and refresh."""
        if failed_tasks: messagebox.showwarning("Run Incomplete", f"Successfully started {success_count} task(s).\n\nFailed to start:\n- " + "\n- ".join(failed_tasks), parent=self)
        elif success_count > 0: messagebox.showinfo("Success", f"Successfully started {success_count} task(s).", parent=self)
        self.status_label.config(text="Run command sent. Refreshing list...")
        self.after(2000, self.refresh_tasks)

    def _stop_task(self):
        """Stops all selected scheduled tasks if they are running."""
        selected_items = self.task_tree.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "Please select one or more tasks to stop.", parent=self)
            return

        task_names = [self.task_tree.item(item, 'values')[0] for item in selected_items if self.task_tree.item(item, 'values')]
        if not task_names:
            messagebox.showerror("Error", "Could not retrieve task names from selection.", parent=self)
            return

        if len(task_names) == 1:
            confirm_message = f"Are you sure you want to stop the task '{task_names[0]}'?"
        else:
            confirm_message = f"Are you sure you want to stop {len(task_names)} selected tasks?"

        if messagebox.askyesno("Confirm Stop", confirm_message, parent=self):
            self.set_buttons_state("disabled")
            self.status_label.config(text=f"Attempting to stop {len(task_names)} task(s)...")
            self.update_idletasks()
            threading.Thread(target=self._stop_tasks_worker, args=(task_names,), daemon=True).start()

    def _stop_tasks_worker(self, task_names):
        """Worker thread to execute schtasks /End for multiple tasks."""
        success_count = 0; failed_tasks = []
        for task_name in task_names:
            try:
                cmd = ["schtasks", "/End", "/TN", task_name]
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False, encoding='cp949', errors='ignore')
                output = (result.stderr or result.stdout).strip()
                if result.returncode == 0 or "ERROR: The specified task is not running." in output:
                    success_count += 1
                else:
                    failed_tasks.append(f"{task_name}: {output}")
            except Exception as e:
                failed_tasks.append(f"{task_name}: {str(e)}")
        self.after(0, self._on_stop_tasks_finished, success_count, failed_tasks)

    def _on_stop_tasks_finished(self, success_count, failed_tasks):
        """Callback to show results after stopping tasks and refresh."""
        if failed_tasks:
            messagebox.showwarning("Stop Incomplete", f"Successfully stopped (or confirmed not running) {success_count} task(s).\n\nFailed to stop:\n- " + "\n- ".join(failed_tasks), parent=self)
        elif success_count > 0:
            messagebox.showinfo("Success", f"Successfully stopped (or confirmed not running) {success_count} task(s).", parent=self)
        self.status_label.config(text="Stop command sent. Refreshing list...")
        self.after(1000, self.refresh_tasks)

    def _disable_task(self):
        self._change_task_enabled_state("DISABLE")

    def _enable_task(self):
        self._change_task_enabled_state("ENABLE")

    def _change_task_enabled_state(self, action):
        """Disables or enables all selected scheduled tasks."""
        selected_items = self.task_tree.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "Please select one or more tasks to change.", parent=self)
            return

        task_names = [self.task_tree.item(item, 'values')[0] for item in selected_items if self.task_tree.item(item, 'values')]
        if not task_names:
            messagebox.showerror("Error", "Could not retrieve task names from selection.", parent=self)
            return

        action_label = action.lower()
        if len(task_names) == 1:
            confirm_message = f"Are you sure you want to {action_label} the task '{task_names[0]}'?"
        else:
            confirm_message = f"Are you sure you want to {action_label} {len(task_names)} selected tasks?"

        if messagebox.askyesno(f"Confirm {action_label.capitalize()}", confirm_message, parent=self):
            self.set_buttons_state("disabled")
            self.status_label.config(text=f"Attempting to {action_label} {len(task_names)} task(s)...")
            self.update_idletasks()
            threading.Thread(target=self._change_state_worker, args=(task_names, action), daemon=True).start()

    def _change_state_worker(self, task_names, action):
        """Worker thread to change the state of multiple tasks."""
        success_count = 0
        failed_tasks = []
        for task_name in task_names:
            try:
                cmd = ["schtasks", "/Change", "/TN", task_name, f"/{action}"]
                subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True, encoding='cp949', errors='ignore')
                success_count += 1
            except Exception:
                failed_tasks.append(task_name)
        self.after(0, self._on_change_state_finished, success_count, failed_tasks, action.lower())

    def _on_change_state_finished(self, success_count, failed_tasks, action_label):
        """Callback to show results after changing state and refresh."""
        if failed_tasks:
            messagebox.showwarning(f"{action_label.capitalize()} Incomplete", f"Successfully {action_label}d {success_count} task(s).\n\nFailed to {action_label}:\n- " + "\n- ".join(failed_tasks), parent=self)
        elif success_count > 0:
            messagebox.showinfo("Success", f"Successfully {action_label}d {success_count} task(s).", parent=self)
        self.refresh_tasks()

    def open_new_schedule_dialog(self):
        try:
            dlg = ScheduleBackupDialog(self)
            self.wait_window(dlg)
            if getattr(dlg, 'action', None) == 'create':
                self.create_scheduled_task(**(dlg.result or {}))
            elif getattr(dlg, 'action', None) == 'delete':
                if name := getattr(dlg, 'task_name', None):
                    if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete the task '{name}'?", parent=self):
                        self.delete_scheduled_task(name)
            self.refresh_tasks()
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {e}", parent=self)

    def open_edit_schedule_dialog(self, event=None):
        selected_item = self.task_tree.focus()
        if not selected_item:
            return

        try:
            task_name = self.task_tree.item(selected_item, 'values')[0]
        except (IndexError, KeyError):
            messagebox.showerror("Error", "Could not retrieve task name from selection.", parent=self)
            return

        config_path = os.path.join(get_schedules_config_dir(), f"{task_name}.json")
        if not os.path.exists(config_path):
            messagebox.showerror("Error", f"Configuration file for '{task_name}' not found. It might be a legacy task. Please delete and recreate it.", parent=self)
            return

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load configuration for '{task_name}':\n{e}", parent=self)
            return

        try:
            dlg = ScheduleBackupDialog(self, initial_data=config_data)
            self.wait_window(dlg)

            if getattr(dlg, 'action', None) == 'create':
                new_config = dlg.result or {}
                new_task_name = new_config.get('task_name')
                if task_name != new_task_name:
                    self.delete_scheduled_task(task_name, show_success_message=False)
                self.create_scheduled_task(**new_config)
            elif getattr(dlg, 'action', None) == 'delete':
                if name := getattr(dlg, 'task_name', None):
                    if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete the task '{name}'?", parent=self):
                        self.delete_scheduled_task(name)
            self.refresh_tasks()
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred while editing the schedule: {e}", parent=self)

    def delete_selected_task(self, event=None):
        """Deletes all selected tasks from the list."""
        selected_items = self.task_tree.selection()
        if not selected_items:
            messagebox.showwarning("Warning", "Please select one or more tasks to delete.", parent=self)
            return

        task_names = []
        for item in selected_items:
            try:
                task_names.append(self.task_tree.item(item, 'values')[0])
            except (IndexError, KeyError):
                continue
        
        if not task_names:
            messagebox.showerror("Error", "Could not retrieve task names from selection.", parent=self)
            return

        if len(task_names) == 1:
            confirm_message = f"Are you sure you want to delete the task '{task_names[0]}'?"
        else:
            confirm_message = f"Are you sure you want to delete {len(task_names)} selected tasks?"

        if messagebox.askyesno("Confirm Delete", confirm_message, parent=self):
            self.set_buttons_state("disabled")
            self.status_label.config(text=f"Deleting {len(task_names)} task(s)...")
            self.update_idletasks()
            threading.Thread(target=self._delete_tasks_worker, args=(task_names,), daemon=True).start()

    def _delete_tasks_worker(self, task_names):
        """Worker thread to delete multiple tasks."""
        success_count = 0
        failed_tasks = []
        for task_name in task_names:
            try:
                self.delete_scheduled_task(task_name, show_success_message=False)
                success_count += 1
            except Exception:
                failed_tasks.append(task_name)
        self.after(0, self._on_delete_tasks_finished, success_count, failed_tasks)

    def _on_delete_tasks_finished(self, success_count, failed_tasks):
        """Callback to show results after deletion and refresh."""
        if failed_tasks:
            messagebox.showwarning("Deletion Incomplete", f"Successfully deleted {success_count} task(s).\n\nFailed to delete:\n- " + "\n- ".join(failed_tasks), parent=self)
        elif success_count > 0:
            messagebox.showinfo("Success", f"Successfully deleted {success_count} task(s).", parent=self)
        self.refresh_tasks()

    def refresh_tasks(self):
        self.status_label.config(text="Loading scheduled tasks..."); self.set_buttons_state("disabled")
        self.task_tree.delete(*self.task_tree.get_children())
        threading.Thread(target=self._fetch_tasks_worker, daemon=True).start()

    def _fetch_tasks_worker(self):
        time.sleep(0.5); tasks = self._get_ezbak_tasks(); self.after(0, self._update_ui_with_tasks, tasks)

    def _get_ezbak_tasks(self):
        tasks = []
        try:
            cmd = ['schtasks', '/Query', '/FO', 'CSV', '/V']
            try: output = subprocess.check_output(cmd, text=True, encoding='cp949', errors='ignore', shell=True, stderr=subprocess.DEVNULL)
            except UnicodeDecodeError: output = subprocess.check_output(cmd, text=True, encoding='utf-8', errors='ignore', shell=True, stderr=subprocess.DEVNULL)
            reader = csv.reader(io.StringIO(output))
            try:
                next(reader)  # Skip header row
            except StopIteration: return []
            # Use fixed indices to avoid issues with OS language differences in headers.
            # schtasks /Query /FO CSV /V columns: 0=HostName, 1=TaskName, 2=Next Run Time, 3=Status, 4=Last Run Time, 5=Last Result
            name_idx, run_idx, status_idx, last_run_idx, last_res_idx = 1, 2, 3, 4, 5
            for row in reader:
                if not row: continue
                try:
                    if len(row) > last_res_idx and 'ezbak' in row[name_idx].lower():
                        tasks.append({
                            'name': row[name_idx].split('\\')[-1],
                            'next_run': row[run_idx],
                            'status': row[status_idx],
                            'last_run_time': row[last_run_idx],
                            'last_run_result': row[last_res_idx]
                        })
                except IndexError: continue
            return tasks
        except (subprocess.CalledProcessError, FileNotFoundError, ValueError): return []

    def _update_ui_with_tasks(self, tasks):
        for task in sorted(tasks, key=lambda x: x['name']):
            tags = ()
            last_result_str = task.get('last_run_result', '0').strip()
            # A non-zero result code indicates failure or an issue.
            if last_result_str != '0':
                try:
                    # Handle decimal and hexadecimal (e.g., '0x1') result codes
                    if int(last_result_str, 0) != 0:
                        tags = ('failed',)
                except (ValueError, TypeError):
                    # If the result is not a valid number (e.g., 'N/A'), do not color it.
                    pass
            self.task_tree.insert("", "end", values=(task['name'], task['next_run'], task['status'], task['last_run_time'], task['last_run_result']), tags=tags)
        self.status_label.config(text=f"Found {len(tasks)} ezBAK scheduled task(s). Ready."); self.set_buttons_state("normal")

    def _build_auto_backup_command(self, task_name):
        try:
            if getattr(sys, 'frozen', False):
                return f'"{sys.executable}" --auto-backup --task-name "{task_name}"'
            else:
                return f'"{sys.executable}" "{os.path.abspath(__file__)}" --auto-backup --task-name "{task_name}"'
        except Exception as e:
            messagebox.showerror("Error", f"Failed to build task command: {e}"); return ''

    def create_scheduled_task(self, **kwargs):
        task_name = kwargs.get('task_name')
        if not task_name: messagebox.showwarning("Warning", "Task Name is required."); return
        config_dir = get_schedules_config_dir(); config_path = os.path.join(config_dir, f"{task_name}.json")
        try:
            with open(config_path, 'w', encoding='utf-8') as f: json.dump(kwargs, f, indent=4)
        except Exception as e: messagebox.showerror("Error", f"Failed to save schedule configuration file:\n{e}"); return

        tr_cmd = self._build_auto_backup_command(task_name=task_name)
        if not tr_cmd: return

        base_cmd = ["schtasks", "/Create", "/TN", task_name, "/TR", tr_cmd, "/ST", kwargs.get('time_str'), "/F"]
        schedule_lower = kwargs.get('schedule', '').lower()
        if schedule_lower == 'daily': base_cmd += ["/SC", "DAILY"]
        elif schedule_lower == 'weekly': base_cmd += ["/SC", "WEEKLY", "/D", ','.join(kwargs.get('days', []))]
        elif schedule_lower.isdigit() and 1 <= int(schedule_lower) <= 31: base_cmd += ["/SC", "MONTHLY", "/D", schedule_lower]
        
        cmd_with_privileges = base_cmd + ["/RL", "HIGHEST"]
        try:
            res = subprocess.run(cmd_with_privileges, shell=True, capture_output=True, text=True, check=False)
            if res.returncode != 0: res = subprocess.run(base_cmd, shell=True, capture_output=True, text=True, check=True)
            messagebox.showinfo("Task Scheduler", f"Task '{task_name}' created successfully.")
        except subprocess.CalledProcessError as e: messagebox.showerror("Error", f"Failed to create task:\n{e.stderr or e.stdout}")
        except Exception as e: messagebox.showerror("Error", f"Failed to create scheduled task:\n{e}")

    def delete_scheduled_task(self, task_name, show_success_message=True):
        try:
            subprocess.run(["schtasks", "/Delete", "/TN", task_name, "/F"], shell=True, capture_output=True, text=True, check=True)
            config_path = os.path.join(get_schedules_config_dir(), f"{task_name}.json")
            if os.path.exists(config_path):
                try: os.remove(config_path)
                except Exception as e:
                    # For batch deletes, just print. For single, show a warning.
                    if show_success_message: messagebox.showwarning("Warning", f"Task '{task_name}' was deleted, but failed to remove its config file:\n{e}", parent=self)
                    else: print(f"WARN: Failed to remove config for '{task_name}': {e}")
            if show_success_message:
                messagebox.showinfo("Task Scheduler", f"Task '{task_name}' deleted successfully.")
        except subprocess.CalledProcessError as e:
            if show_success_message: messagebox.showerror("Error", f"Failed to delete task:\n{e.stderr or e.stdout}", parent=self)
            else: raise
        except Exception as e:
            if show_success_message: messagebox.showerror("Error", f"Failed to delete scheduled task:\n{e}", parent=self)
            else: raise

if __name__ == "__main__":
    import traceback

    def _find_available_drive_letter():
        """사용 가능한 드라이브 문자를 찾아 반환 (Z부터 역순으로)"""
        try:
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for i in range(25, 1, -1):  # Z부터 C까지 역순
                if not (bitmask & (1 << i)):
                    return f"{chr(65 + i)}:"
        except Exception:
            # Fallback: 직접 확인
            for letter in "ZYXWVUTSRQPONMLKJIHGFEDC":
                if not os.path.exists(f"{letter}:\\"):
                    return f"{letter}:"
        return None

    def _get_mounted_drives_for_guid(guid):
        """주어진 GUID가 마운트된 모든 드라이브 문자 반환

        Returns:
            list: 마운트된 드라이브 문자 리스트 (예: ['D:', 'E:'])
        """
        mounted_drives = []
        try:
            env = os.environ.copy()
            env['LC_ALL'] = 'C'
            output = subprocess.check_output("mountvol", text=True, encoding='utf-8',
                                             errors='ignore', shell=True, env=env)

            current_guid = None
            guid_pattern = re.compile(r"(\\\\\?\\Volume\{[a-fA-F0-9-]+\}\\)")
            drive_pattern = re.compile(r'^([A-Za-z]):\\$')

            for line in output.splitlines():
                match = guid_pattern.search(line)
                if match:
                    current_guid = match.group(1)
                elif current_guid and current_guid.lower() == guid.lower():
                    if line.startswith('    '):
                        stripped = line.strip()
                        drive_match = drive_pattern.match(stripped)
                        if drive_match:
                            mounted_drives.append(f"{drive_match.group(1)}:")
                    else:
                        current_guid = None
        except Exception as e:
            log_message(f"WARN: Failed to check mounted drives: {e}")

        return mounted_drives

    def _run_headless_if_requested():
        if '--auto-backup' in sys.argv:
            def _get_arg(flag):
                try: i = sys.argv.index(flag); return sys.argv[i+1]
                except (ValueError, IndexError): return None
            task_name = _get_arg('--task-name')
            if not task_name: sys.exit(1)

            config_path = os.path.join(get_schedules_config_dir(), f"{task_name}.json")
            if not os.path.exists(config_path):
                log_message(f"Config file not found: {config_path}"); sys.exit(1)
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
            except Exception as e:
                log_message(f"Failed to load config file {config_path}: {e}"); sys.exit(1)

            mount_info = config_data.get('mount_info')
            temp_drive_mounted = None  # 우리가 새로 마운트한 임시 드라이브
            original_mounts = []  # 원래 마운트되어 있던 드라이브들
            exit_code = 0

            # --- MOUNT PHASE ---
            if mount_info:
                guid = mount_info.get('guid')

                if not guid:
                    log_message("FATAL: Volume GUID not found in mount_info.")
                    sys.exit(1)

                # ★ 1단계: 기존 마운트 확인
                original_mounts = _get_mounted_drives_for_guid(guid)

                if original_mounts:
                    log_message(f"Volume {guid} is currently mounted at: {', '.join(original_mounts)}")
                    log_message(f"Unmounting existing mount points...")

                    # ★ 2단계: 기존 마운트 모두 해제
                    for drive in original_mounts:
                        try:
                            cmd = ["mountvol", drive, "/D"]
                            subprocess.run(cmd, shell=True, check=True, capture_output=True,
                                           text=True, encoding='cp949', errors='ignore')
                            log_message(f"Successfully unmounted {drive}.")
                        except Exception as e:
                            log_message(f"WARN: Failed to unmount {drive}: {e}")
                            # 계속 진행 (다른 마운트는 해제 시도)
                else:
                    log_message(f"Volume {guid} is not currently mounted.")

                # ★ 3단계: 임시 드라이브 찾기
                temp_drive = _find_available_drive_letter()

                if not temp_drive:
                    log_message("FATAL: No available drive letter for temporary mount.")
                    # 실패 시 원래 마운트 복구 시도
                    if original_mounts:
                        log_message("Attempting to restore original mounts...")
                        for drive in original_mounts:
                            try:
                                cmd = ["mountvol", drive, guid]
                                subprocess.run(cmd, shell=True, check=True, capture_output=True,
                                               text=True, encoding='cp949', errors='ignore')
                                log_message(f"Restored mount: {drive}")
                            except Exception:
                                pass
                    sys.exit(1)

                log_message(f"Found available drive letter: {temp_drive}")
                log_message(f"Attempting to mount volume {guid} to {temp_drive}...")

                # ★ 4단계: 임시 드라이브에 마운트
                try:
                    cmd = ["mountvol", temp_drive, guid]
                    subprocess.run(cmd, shell=True, check=True, capture_output=True,
                                   text=True, encoding='cp949', errors='ignore')
                    log_message(f"Successfully mounted {guid} to {temp_drive}.")
                    temp_drive_mounted = temp_drive
                    config_data['dest'] = temp_drive

                except subprocess.CalledProcessError as e:
                    log_message(f"FATAL: Failed to mount volume. Error: {e.stderr or e.stdout}")
                    # 실패 시 원래 마운트 복구 시도
                    if original_mounts:
                        log_message("Attempting to restore original mounts...")
                        for drive in original_mounts:
                            try:
                                cmd = ["mountvol", drive, guid]
                                subprocess.run(cmd, shell=True, check=True, capture_output=True,
                                               text=True, encoding='cp949', errors='ignore')
                                log_message(f"Restored mount: {drive}")
                            except Exception:
                                pass
                    sys.exit(1)
                except Exception as e:
                    log_message(f"FATAL: An unexpected error occurred during mount: {e}")
                    sys.exit(1)

            dest = config_data.get('dest')
            
            # For Direct FTP, use a persistent log folder instead of the temp backup folder
            if config_data.get('direct_ftp'):
                # Save logs to Desktop
                log_dir = os.path.join(os.path.expanduser('~'), 'Desktop')
                os.makedirs(log_dir, exist_ok=True)
                dest = log_dir
                config_data['dest'] = dest # Update config so runner knows where logs are
                
            if not dest:
                log_message("FATAL: Destination 'dest' not found in config.")
                sys.exit(1)

            # Instantiate runner to get the proper base name for the log file.
            runner = HeadlessBackupRunner(config_data)
            log_file_path = os.path.join(dest, f"{runner._get_base_name()}_backup_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.log")

            log_file_handle = None
            original_stdout, original_stderr = sys.stdout, sys.stderr
            try:
                os.makedirs(dest, exist_ok=True)
                log_file_handle = open(log_file_path, 'w', encoding='utf-8')
                sys.stdout = log_file_handle; sys.stderr = log_file_handle

                log_message(f"--- Headless execution started for task: {task_name} ---")
                runner.run_backup()
            except Exception as e:
                log_fn = log_message if log_file_handle else print
                log_fn("--- FATAL ERROR ---")
                if log_file_handle: traceback.print_exc(file=sys.stdout)
                else: traceback.print_exc()
                exit_code = 1
                show_notification(
                    title="ezBAK Backup Failed",
                    message=f"Task '{task_name}' encountered a fatal error. Check logs for details.",
                    button_text="Open Log Folder",
                    button_argument=dest if not temp_drive_mounted else None
                )
                email_config = config_data.get('email_notification', {})
                if email_config.get('enabled') and email_config.get('notify_on_failure', True):
                    log_message("Attempting to send failure notification email...")
                    try:
                        error_details = traceback.format_exc()
                        email_subject = f"[FAIL] ezBAK Backup Task Failed: {task_name}"
                        email_body = (
                            f"The scheduled backup task '{task_name}' failed.\n\n"
                            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                            f"Volume GUID: {mount_info.get('guid') if mount_info else 'N/A'}\n"
                            f"Temporary Drive: {temp_drive_mounted or 'N/A'}\n\n"
                            f"--- Error Details ---\n{error_details}\n\n"
                            f"A detailed log may be available at: {log_file_path}"
                        )
                        send_email_notification(email_subject, email_body, email_config)
                    except Exception as email_e:
                        log_fn(f"FATAL: Could not prepare or send email. Error: {email_e}")
            finally:
                if log_file_handle:
                    log_message(f"--- Headless execution finished ---")
                    log_file_handle.close()
                sys.stdout, sys.stderr = original_stdout, original_stderr

            # --- UNMOUNT PHASE ---
            # ★ 5단계: 임시 드라이브 언마운트
            if temp_drive_mounted:
                log_message(f"Attempting to unmount temporary drive {temp_drive_mounted}...")
                try:
                    cmd = ["mountvol", temp_drive_mounted, "/D"]
                    subprocess.run(cmd, shell=True, check=True, capture_output=True,
                                   text=True, encoding='cp949', errors='ignore')
                    log_message(f"Successfully unmounted {temp_drive_mounted}.")
                except Exception as e:
                    log_message(f"ERROR: Failed to unmount drive {temp_drive_mounted}: {e}")

            # ★ 6단계: 원래 마운트 복구 (선택사항)
            # if original_mounts:
            #     log_message(f"Restoring original mount points: {', '.join(original_mounts)}...")
            #     for drive in original_mounts:
            #         try:
            #             cmd = ["mountvol", drive, guid]
            #             subprocess.run(cmd, shell=True, check=True, capture_output=True,
            #                            text=True, encoding='cp949', errors='ignore')
            #             log_message(f"Restored mount: {drive}")
            #         except Exception as e:
            #             log_message(f"WARN: Failed to restore mount {drive}: {e}")

    # 1. 기존 마운트 확인 (D:에 마운트되어 있음)
    # ↓
    # 2. 기존 마운트 해제 (D: 언마운트)
    # ↓
    # 3. 사용 가능한 임시 드라이브 찾기 (Z:)
    # ↓
    # 4. 임시 드라이브에 마운트 (Z:에 마운트)
    # ↓
    # 5. 백업 진행 (Z:로 백업)
    # ↓
    # 6. 임시 드라이브 언마운트 (Z: 언마운트)
    # ↓
    # 7. 완료 (원래대로 마운트 안 된 상태 유지)

            sys.exit(exit_code)

    _run_headless_if_requested()

    def is_admin():
        try: return ctypes.windll.shell32.IsUserAnAdmin()
        except: return False

    if not is_admin():
        try:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        except Exception as e:
            messagebox.showerror("Administrator Privileges Required", f"Failed to elevate privileges: {e}\nPlease run this program as an administrator.")
    else:
        app = SchedulerApp()
        app.mainloop()