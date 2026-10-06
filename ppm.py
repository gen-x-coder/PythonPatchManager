import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QIcon, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QProgressBar, QTextEdit, QFrame, 
    QFileDialog, QMessageBox, QStackedWidget, QListWidget, 
    QSizePolicy, QLineEdit, QCheckBox, QDialog, QScrollArea
)

VERSION = "0.4.3"

# --- DYNAMISCHE PADEN ---
SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_FILE = SCRIPT_DIR / "ppm.json"
ICONS_DIR = SCRIPT_DIR / "icons"

# --- QSS STYLING ---
QSS_STYLE = """
QMainWindow {
    background-color: #f4f5f7;
}
QWidget#sidebar {
    background-color: #f4f5f7;
    border-right: 1px solid #e2e8f0;
}
QWidget#main_content {
    background-color: #ffffff;
}
QListWidget#nav_list {
    background-color: transparent;
    border: none;
    font-size: 13px;
    color: #4a5568;
    outline: none;
}
QListWidget#nav_list::item {
    padding: 10px 16px;
    border-radius: 6px;
    margin: 2px 8px;
}
QListWidget#nav_list::item:selected {
    background-color: #ebf4ff;
    color: #2b6cb0;
    font-weight: bold;
}
QListWidget#nav_list::item:hover:!selected {
    background-color: #edf2f7;
}
QLabel#page_title {
    font-size: 16px;
    font-weight: bold;
    color: #1a202c;
    margin-bottom: 16px;
}
QLabel#hero_filename {
    font-size: 18px;
    font-weight: bold;
    color: #2b6cb0;
    font-family: Consolas, monospace;
}
QLabel#hero_info {
    font-size: 12px;
    color: #718096;
    margin-top: 4px;
}
QLabel#status_text {
    font-size: 12px;
    color: #4a5568;
    font-style: italic;
}
QPushButton {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
    color: #2d3748;
}
QPushButton:hover {
    background-color: #edf2f7;
    border-color: #cbd5e0;
}
QPushButton#primary_btn {
    background-color: #3182ce;
    color: #ffffff;
    border: 1px solid #3182ce;
    font-weight: bold;
}
QPushButton#primary_btn:hover {
    background-color: #2b6cb0;
    border-color: #2b6cb0;
}
QPushButton#primary_btn:disabled {
    background-color: #a0aec0;
    border-color: #a0aec0;
    color: #ffffff;
}
QPushButton#secondary_btn {
    background-color: #48bb78;
    color: #ffffff;
    border: 1px solid #48bb78;
    font-weight: bold;
}
QPushButton#secondary_btn:hover {
    background-color: #38a169;
    border-color: #38a169;
}
QPushButton#secondary_btn:disabled {
    background-color: #a0aec0;
    border-color: #a0aec0;
    color: #ffffff;
}
QPushButton#small_action_btn {
    padding: 4px 10px;
    font-size: 11px;
    border-radius: 4px;
}
QProgressBar {
    border: 1px solid #e2e8f0;
    border-radius: 4px;
    text-align: center;
    background-color: #edf2f7;
    height: 8px;
    font-size: 10px;
    color: transparent;
}
QProgressBar::chunk {
    background-color: #3182ce;
    border-radius: 3px;
}
QTextEdit#log_area {
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    background-color: #1e1e1e;
    color: #d4d4d4;
    font-family: Consolas, monospace;
    font-size: 12px;
    padding: 8px;
}
QLineEdit {
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    background-color: #ffffff;
}
QLineEdit:focus {
    border-color: #3182ce;
    outline: none;
}
QCheckBox {
    font-size: 13px;
    color: #4a5568;
    spacing: 8px;
}
QFrame#card {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 16px;
}
QFrame#history_item {
    background-color: #f8fafc;
    border: 1px solid #edf2f7;
    border-radius: 6px;
    padding: 8px 12px;
}
QLabel#form_label {
    font-size: 12px;
    color: #718096;
    font-weight: bold;
}

QDialog#success_dialog {
    background-color: #f4f5f7;
}
QDialog#success_dialog QLabel#dialog_title {
    font-size: 16px;
    font-weight: bold;
    color: #1a202c;
}
QDialog#success_dialog QLabel#dialog_filename {
    font-size: 12px;
    color: #718096;
    font-family: Consolas, monospace;
}
QDialog#success_dialog QLabel#dialog_stats {
    font-size: 13px;
    color: #2d3748;
    line-height: 1.5;
}
"""

class AppMonitor(QThread):
    app_running = Signal()
    app_crashed = Signal(str)
    app_closed = Signal()

    def __init__(self, proc, entry_point):
        super().__init__()
        self.proc = proc
        self.entry_point = entry_point

    def run(self):
        try:
            _, stderr = self.proc.communicate(timeout=1.5)
            if self.proc.returncode != 0:
                self.app_crashed.emit(stderr)
            else:
                self.app_closed.emit()
        except subprocess.TimeoutExpired:
            self.app_running.emit()
            self.proc.wait()
            self.app_closed.emit()


class ExtractWorker(QThread):
    progress_update = Signal(int, str)
    finished_signal = Signal(bool, object, str, Path)

    def __init__(self, zip_path: Path, target_dir: Path, overwrite: bool):
        super().__init__()
        self.zip_path = zip_path
        self.target_dir = target_dir
        self.overwrite = overwrite

    def run(self):
        stats = {"new_files": 0, "new_dirs": 0, "overwritten": 0, "skipped": 0, "errors": 0}
        target_dir_abs = self.target_dir.resolve()
        extracted_files = []

        try:
            target_dir_abs.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(self.zip_path, "r") as zf:
                members = zf.namelist()
                total = len(members) or 1
                
                root_prefix = ""
                if members:
                    first_nested = next((m for m in members if '/' in m), None)
                    if first_nested:
                        potential_root = first_nested.split('/')[0] + '/'
                        if all(m.startswith(potential_root) or m == potential_root.rstrip('/') for m in members):
                            root_prefix = potential_root
                
                for i, member in enumerate(members, 1):
                    clean_member = member[len(root_prefix):] if member.startswith(root_prefix) else member
                    
                    if not clean_member and member.endswith('/'):
                        pct = int(i / total * 100)
                        self.progress_update.emit(pct, f"Overslaan root map: {member}")
                        continue

                    dest = (target_dir_abs / clean_member).resolve()
                    
                    try:
                        if not dest.is_relative_to(target_dir_abs):
                            stats["errors"] += 1
                            continue
                    except ValueError:
                        stats["errors"] += 1
                        continue

                    if clean_member.endswith("/") or clean_member.endswith("\\"):
                        if not dest.exists():
                            dest.mkdir(parents=True, exist_ok=True)
                            stats["new_dirs"] += 1
                        pct = int(i / total * 100)
                        self.progress_update.emit(pct, f"Map aangemaakt: {clean_member}")
                        continue

                    dest.parent.mkdir(parents=True, exist_ok=True)
                    exists = dest.exists()
                    
                    if exists and not self.overwrite:
                        stats["skipped"] += 1
                        pct = int(i / total * 100)
                        self.progress_update.emit(pct, f"Overgeslagen: {clean_member}")
                        continue

                    try:
                        with zf.open(member) as source, open(dest, "wb") as target_file:
                            shutil.copyfileobj(source, target_file)
                        extracted_files.append(dest)
                        if exists:
                            stats["overwritten"] += 1
                        else:
                            stats["new_files"] += 1
                    except Exception:
                        stats["errors"] += 1

                    pct = int(i / total * 100)
                    self.progress_update.emit(pct, f"Verwerken: {clean_member}")

            missing_after_extract = [f for f in extracted_files if not f.exists()]
            if missing_after_extract:
                stats["errors"] += len(missing_after_extract)

            self.finished_signal.emit(True, stats, self.zip_path.name, target_dir_abs)
        except Exception as e:
            self.finished_signal.emit(False, str(e), self.zip_path.name, target_dir_abs)


class SuccessDialog(QDialog):
    def __init__(self, parent, filename: str, stats: dict, entry_point: str):
        super().__init__(parent)
        self.setObjectName("success_dialog")
        self.setWindowTitle("Patch Geplaatst")
        self.setFixedSize(420, 280)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Patch succesvol geïnstalleerd")
        title.setObjectName("dialog_title")
        layout.addWidget(title)

        fname = QLabel(filename)
        fname.setObjectName("dialog_filename")
        layout.addWidget(fname)

        stats_card = QFrame()
        stats_card.setObjectName("card")
        stats_layout = QVBoxLayout(stats_card)
        
        stats_text = QLabel(
            f"{stats['new_files']} nieuwe bestanden\n"
            f"{stats['overwritten']} overschreven bestanden\n"
            f"{stats['skipped']} overgeslagen"
        )
        stats_text.setObjectName("dialog_stats")
        stats_layout.addWidget(stats_text)
        layout.addWidget(stats_card)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        close_btn = QPushButton("Sluiten")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(close_btn)

        start_btn = QPushButton(f"Start {entry_point}")
        start_btn.setObjectName("secondary_btn")
        start_btn.clicked.connect(self.accept)
        btn_layout.addWidget(start_btn)

        layout.addLayout(btn_layout)

        self.start_clicked = False
        self.accepted.connect(lambda: setattr(self, 'start_clicked', True))


class PythonPatchManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Python Patch Manager")
        self.resize(900, 700)
        self.setMinimumSize(700, 550)

        icon_path = ICONS_DIR / "export.svg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.config = self._load_config()
        self.latest_file: Path | None = None
        self.recent_candidates: list[Path] = []
        self.is_extracting = False
        self.worker = None
        self.app_monitor = None

        self._init_ui()
        self._scan_and_update()
        
        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self._scan_and_update)
        
        if self.config.get("auto_scan", True):
            self.scan_timer.start(3000)

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 24, 16, 24)

        app_title = QLabel("Python Patch Manager")
        app_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #1a202c; margin-bottom: 24px;")
        sidebar_layout.addWidget(app_title)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("nav_list")
        self.nav_list.addItem("Dashboard")
        self.nav_list.addItem("Instellingen")
        self.nav_list.addItem("Logboek")
        
        icon_files = ["insert.svg", "edit.svg", "history.svg"]
        for i in range(self.nav_list.count()):
            item = self.nav_list.item(i)
            icon_path = ICONS_DIR / icon_files[i]
            if icon_path.exists():
                item.setIcon(QIcon(str(icon_path)))
                
        self.nav_list.setCurrentRow(0)
        self.nav_list.currentRowChanged.connect(self._switch_page)
        sidebar_layout.addWidget(self.nav_list)
        sidebar_layout.addStretch()

        version_label = QLabel(f"v{VERSION}")
        version_label.setStyleSheet("font-size: 11px; color: #a0aec0;")
        sidebar_layout.addWidget(version_label)

        main_layout.addWidget(sidebar)

        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("main_content")
        
        self._build_dashboard_page()
        self._build_settings_page()
        self._build_log_page()

        main_layout.addWidget(self.content_stack, 1)

    def _build_dashboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(20)

        title = QLabel("Dashboard")
        title.setObjectName("page_title")
        layout.addWidget(title)

        # Actieve patch card
        self.hero_card = QFrame()
        self.hero_card.setObjectName("card")
        hero_layout = QVBoxLayout(self.hero_card)
        
        hero_header = QLabel("LAATSTE PATCH")
        hero_header.setStyleSheet("font-size: 11px; font-weight: bold; color: #a0aec0; letter-spacing: 1px;")
        hero_layout.addWidget(hero_header)

        self.file_label = QLabel("(nog niets gevonden)")
        self.file_label.setObjectName("hero_filename")
        hero_layout.addWidget(self.file_label)

        self.info_label = QLabel("")
        self.info_label.setObjectName("hero_info")
        hero_layout.addWidget(self.info_label)

        layout.addWidget(self.hero_card)

        # Actieknoppen
        btn_layout = QHBoxLayout()
        self.extract_btn = QPushButton("Nu Uitpakken")
        self.extract_btn.setObjectName("primary_btn")
        self.extract_btn.setEnabled(False)
        self.extract_btn.clicked.connect(lambda: self._start_extract(self.latest_file))
        btn_layout.addWidget(self.extract_btn)

        self.start_app_btn = QPushButton("Start Applicatie")
        self.start_app_btn.setObjectName("secondary_btn")
        self.start_app_btn.setEnabled(False)
        self.start_app_btn.clicked.connect(self._start_app_manually)
        btn_layout.addWidget(self.start_app_btn)

        self.open_dir_btn = QPushButton("Map Openen")
        self.open_dir_btn.clicked.connect(self._open_target_folder)
        btn_layout.addWidget(self.open_dir_btn)

        self.refresh_btn = QPushButton("Vernieuwen")
        self.refresh_btn.clicked.connect(self._scan_and_update)
        btn_layout.addWidget(self.refresh_btn)

        layout.addLayout(btn_layout)

        self.status_label = QLabel("Wachten op instellingen...")
        self.status_label.setObjectName("status_text")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # SECTIE: EERDERE VERSIES
        history_header = QLabel("EERDERE VERSIES IN BRONMAP")
        history_header.setStyleSheet("font-size: 11px; font-weight: bold; color: #a0aec0; letter-spacing: 1px; margin-top: 8px;")
        layout.addWidget(history_header)

        self.history_container = QVBoxLayout()
        self.history_container.setSpacing(8)
        layout.addLayout(self.history_container)

        layout.addStretch()
        self.content_stack.addWidget(page)

    def _build_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(20)

        title = QLabel("Instellingen")
        title.setObjectName("page_title")
        layout.addWidget(title)

        form_layout = QVBoxLayout()
        form_layout.setSpacing(16)

        src_label = QLabel("Bronmap (Downloads)")
        src_label.setObjectName("form_label")
        form_layout.addWidget(src_label)
        src_row = QHBoxLayout()
        self.source_input = QLineEdit(self._get_normalized_path(self.config.get("source_dir", "")))
        src_row.addWidget(self.source_input)
        src_browse = QPushButton("Bladeren...")
        src_browse.clicked.connect(lambda: self._browse_dir(self.source_input, "Kies bronmap", is_dir=True))
        src_row.addWidget(src_browse)
        form_layout.addLayout(src_row)

        tgt_label = QLabel("Doelmap (Project)")
        tgt_label.setObjectName("form_label")
        form_layout.addWidget(tgt_label)
        tgt_row = QHBoxLayout()
        self.target_input = QLineEdit(self._get_normalized_path(self.config.get("target_dir", "")))
        self.target_input.textChanged.connect(self._on_target_dir_changed)
        tgt_row.addWidget(self.target_input)
        tgt_browse = QPushButton("Bladeren...")
        tgt_browse.clicked.connect(lambda: self._browse_dir(self.target_input, "Kies doelmap", is_dir=True))
        tgt_row.addWidget(tgt_browse)
        form_layout.addLayout(tgt_row)

        ep_label = QLabel("Opstartbestand")
        ep_label.setObjectName("form_label")
        form_layout.addWidget(ep_label)
        ep_row = QHBoxLayout()
        self.entry_point_input = QLineEdit(self.config.get("entry_point", "main.py"))
        ep_row.addWidget(self.entry_point_input)
        self.entry_point_browse = QPushButton("Bladeren...")
        self.entry_point_browse.clicked.connect(self._browse_entry_point)
        ep_row.addWidget(self.entry_point_browse)
        form_layout.addLayout(ep_row)

        self.overwrite_check = QCheckBox("Bestaande bestanden overschrijven")
        self.overwrite_check.setChecked(self.config.get("overwrite", True))
        form_layout.addWidget(self.overwrite_check)

        pat_label = QLabel("Zoekpatroon")
        pat_label.setObjectName("form_label")
        form_layout.addWidget(pat_label)
        self.pattern_input = QLineEdit(self.config.get("pattern", ""))
        form_layout.addWidget(self.pattern_input)

        self.auto_scan_check = QCheckBox("Automatisch scannen op nieuwe patches")
        self.auto_scan_check.setChecked(self.config.get("auto_scan", True))
        self.auto_scan_check.stateChanged.connect(self._toggle_auto_scan)
        form_layout.addWidget(self.auto_scan_check)

        help_text = QLabel("Bijv. Zoekpatroon: QuietWriter_*_changed_files.zip  |  Opstartbestand: main.py")
        help_text.setStyleSheet("font-size: 11px; color: #a0aec0; margin-top: 8px;")
        form_layout.addWidget(help_text)

        layout.addLayout(form_layout)
        layout.addStretch()
        self.content_stack.addWidget(page)
        
        self._on_target_dir_changed()

    def _on_target_dir_changed(self):
        target_dir = self._get_normalized_path(self.target_input.text())
        self.entry_point_browse.setEnabled(bool(target_dir) and Path(target_dir).exists())

    def _toggle_auto_scan(self, state):
        is_checked = bool(state)
        self.config["auto_scan"] = is_checked
        if is_checked:
            self.scan_timer.start(3000)
        else:
            self.scan_timer.stop()
        self._save_config()

    def _browse_entry_point(self):
        target_dir = self._get_normalized_path(self.target_input.text())
        if not target_dir or not Path(target_dir).exists():
            return
            
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Kies opstartbestand", target_dir, "Python Files (*.py)"
        )
        if file_path:
            self.entry_point_input.setText(Path(file_path).name)
            self._save_config()

    def _build_log_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 32, 32, 32)

        title = QLabel("Logboek")
        title.setObjectName("page_title")
        layout.addWidget(title)

        self.log_area = QTextEdit()
        self.log_area.setObjectName("log_area")
        self.log_area.setReadOnly(True)
        layout.addWidget(self.log_area)

        self.content_stack.addWidget(page)

    def _switch_page(self, index):
        self.content_stack.setCurrentIndex(index)

    def _load_config(self) -> dict:
        default_config = {
            "source_dir": "", "target_dir": "", "pattern": "",
            "entry_point": "main.py", "overwrite": True, "auto_scan": True
        }
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_config.update(data)
            except Exception:
                pass
        return default_config

    def _save_config(self):
        self.config["source_dir"] = self._get_normalized_path(self.source_input.text())
        self.config["target_dir"] = self._get_normalized_path(self.target_input.text())
        self.config["pattern"] = self.pattern_input.text().strip()
        self.config["entry_point"] = self.entry_point_input.text().strip() or "main.py"
        self.config["overwrite"] = self.overwrite_check.isChecked()
        self.config["auto_scan"] = self.auto_scan_check.isChecked()
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
        except Exception:
            pass

    def _get_normalized_path(self, path_str: str) -> str:
        cleaned = path_str.strip()
        return os.path.normpath(cleaned) if cleaned else ""

    def _browse_dir(self, line_edit: QLineEdit, title: str, is_dir: bool = True):
        if is_dir:
            path = QFileDialog.getExistingDirectory(self, title, line_edit.text() or str(Path.home()))
        else:
            path, _ = QFileDialog.getOpenFileName(self, title, line_edit.text() or str(Path.home()))
            
        if path:
            line_edit.setText(self._get_normalized_path(path))
            self._save_config()
            self._scan_and_update()

    def _validate_inputs(self) -> bool:
        return bool(
            self.source_input.text().strip() and 
            self.target_input.text().strip() and 
            self.pattern_input.text().strip() and 
            self.entry_point_input.text().strip()
        )

    def _find_candidates(self) -> list[Path]:
        if not self._validate_inputs():
            return []
        source = Path(self._get_normalized_path(self.source_input.text()))
        if not source.exists():
            return []
        pattern = self.pattern_input.text().strip()
        try:
            candidates = [f for f in source.glob(pattern) if f.is_file()]
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return candidates
        except Exception:
            return []

    def _scan_and_update(self):
        if self.is_extracting:
            return
        if not self._validate_inputs():
            self.file_label.setText("(instellingen niet compleet)")
            self.info_label.setText("Vul alle velden in bij Instellingen")
            self.extract_btn.setEnabled(False)
            self.start_app_btn.setEnabled(False)
            self.status_label.setText("Wachten op configuratie...")
            self._clear_history_ui()
            return

        candidates = self._find_candidates()
        latest = candidates[0] if candidates else None
        
        if latest != self.latest_file or candidates[1:5] != self.recent_candidates:
            self.latest_file = latest
            self.recent_candidates = candidates[1:5] if len(candidates) > 1 else []

            if latest:
                mtime = datetime.fromtimestamp(latest.stat().st_mtime)
                size_mb = latest.stat().st_size / (1024 * 1024)
                self.file_label.setText(latest.name)
                self.info_label.setText(f"{size_mb:.2f} MB  |  Gewijzigd op {mtime:%d-%m-%Y %H:%M:%S}")
                self.extract_btn.setEnabled(True)
                self.status_label.setText("Klaar om uit te pakken.")
            else:
                self.file_label.setText("(geen matchend bestand)")
                self.info_label.setText("Geen ZIP gevonden die voldoet aan het zoekpatroon")
                self.extract_btn.setEnabled(False)
                self.status_label.setText("Scannen naar nieuwe bestanden...")

            self._update_history_ui()

        target_dir = Path(self._get_normalized_path(self.target_input.text()))
        entry_point = self.entry_point_input.text().strip() or "main.py"
        if (target_dir / entry_point).exists():
            self.start_app_btn.setEnabled(True)
        else:
            self.start_app_btn.setEnabled(False)

    def _clear_history_ui(self):
        while self.history_container.count():
            item = self.history_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _update_history_ui(self):
        self._clear_history_ui()
        
        if not self.recent_candidates:
            empty_lbl = QLabel("Geen eerdere versies gevonden.")
            empty_lbl.setStyleSheet("font-size: 12px; color: #a0aec0; font-style: italic;")
            self.history_container.addWidget(empty_lbl)
            return

        for zip_path in self.recent_candidates:
            item_frame = QFrame()
            item_frame.setObjectName("history_item")
            item_layout = QHBoxLayout(item_frame)
            item_layout.setContentsMargins(8, 6, 8, 6)

            mtime = datetime.fromtimestamp(zip_path.stat().st_mtime)
            size_mb = zip_path.stat().st_size / (1024 * 1024)

            info_vbox = QVBoxLayout()
            info_vbox.setSpacing(2)

            fn_lbl = QLabel(zip_path.name)
            fn_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #2d3748; font-family: Consolas, monospace;")
            info_vbox.addWidget(fn_lbl)

            meta_lbl = QLabel(f"{size_mb:.2f} MB  |  {mtime:%d-%m-%Y %H:%M:%S}")
            meta_lbl.setStyleSheet("font-size: 11px; color: #a0aec0;")
            info_vbox.addWidget(meta_lbl)

            item_layout.addLayout(info_vbox, 1)

            btn = QPushButton("Uitpakken")
            btn.setObjectName("small_action_btn")
            btn.clicked.connect(lambda _, p=zip_path: self._start_extract(p))
            item_layout.addWidget(btn)

            self.history_container.addWidget(item_frame)

    def _open_target_folder(self):
        target_str = self._get_normalized_path(self.target_input.text())
        if target_str and Path(target_str).exists():
            os.startfile(target_str)
        else:
            QMessageBox.warning(self, "Niet gevonden", f"De opgegeven doelmap bestaat nog niet:\n{target_str}")

    def _start_extract(self, zip_to_extract: Path | None = None):
        target_zip = zip_to_extract or self.latest_file
        
        if not target_zip or not target_zip.exists():
            QMessageBox.warning(self, "Fout", "Het geselecteerde bestand bestaat niet meer.")
            self._scan_and_update()
            return
        if self.is_extracting:
            return

        self._save_config()
        self.is_extracting = True
        self.extract_btn.setEnabled(False)
        self.start_app_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Uitpakken gestart ({target_zip.name})...")
        self.log_area.clear()

        target = Path(self._get_normalized_path(self.target_input.text()))
        self.worker = ExtractWorker(target_zip, target, self.overwrite_check.isChecked())
        self.worker.progress_update.connect(self._update_progress)
        self.worker.finished_signal.connect(self._extract_done)
        self.worker.start()

    def _update_progress(self, value: int, status: str):
        self.progress_bar.setValue(value)
        self.status_label.setText(status)

    def _log_text(self, text: str):
        self.log_area.append(text)
        scrollbar = self.log_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _extract_done(self, success: bool, data, filename: str, target_dir: Path):
        self.is_extracting = False
        self.progress_bar.setValue(100 if success else 0)
        self.extract_btn.setEnabled(True)
        self._scan_and_update()
        entry_point = self.entry_point_input.text().strip() or "main.py"

        if success:
            stats = data
            self.status_label.setText("Uitpakken voltooid.")
            log_lines = [
                f"[{datetime.now():%H:%M:%S}] PATCH GEPLAATST: {filename}",
                f" Doelmap: {target_dir}",
                f" Resultaat: {stats['new_files']} nieuw, {stats['overwritten']} overschreven, {stats['skipped']} overgeslagen."
            ]
            target_entry = target_dir / entry_point
            if not target_entry.exists():
                log_lines.append(f" WAARSCHUWING: '{entry_point}' niet gevonden in root van doelmap!")
            if stats["errors"]:
                log_lines.append(f" Fouten opgetreden: {stats['errors']}")
            
            self._log_text("\n".join(log_lines))
            self._show_success_dialog(filename, stats, target_dir, entry_point)
        else:
            self.status_label.setText("Fout opgetreden")
            self._log_text(f"[{datetime.now():%H:%M:%S}] FOUT:\n{data}")
            QMessageBox.critical(self, "Fout bij uitpakken", str(data))

    def _show_success_dialog(self, filename: str, stats: dict, target_dir: Path, entry_point: str):
        dialog = SuccessDialog(self, filename, stats, entry_point)
        result = dialog.exec()
        
        if dialog.start_clicked:
            self._launch_app(target_dir, entry_point)

    def _start_app_manually(self):
        target_dir = Path(self._get_normalized_path(self.target_input.text()))
        entry_point = self.entry_point_input.text().strip() or "main.py"
        self._launch_app(target_dir, entry_point)

    def _launch_app(self, target_dir: Path, entry_point: str):
        target_entry = target_dir / entry_point
        if not target_entry.exists():
            QMessageBox.warning(self, "Niet gevonden", f"Kan '{entry_point}' niet vinden in:\n{target_dir}")
            return

        self.start_app_btn.setEnabled(False)
        self.status_label.setText(f"Starten van {entry_point}...")
        self._log_text(f"[{datetime.now():%H:%M:%S}] Starten van {entry_point}...")

        try:
            proc = subprocess.Popen(
                [sys.executable, entry_point],
                cwd=str(target_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.app_monitor = AppMonitor(proc, entry_point)
            self.app_monitor.app_running.connect(self._handle_app_running)
            self.app_monitor.app_crashed.connect(self._handle_app_crashed)
            self.app_monitor.app_closed.connect(self._handle_app_closed)
            self.app_monitor.start()

        except Exception as e:
            self.status_label.setText("Fout bij opstarten")
            self._log_text(f"[{datetime.now():%H:%M:%S}] Kon {entry_point} niet starten: {e}")
            QMessageBox.critical(self, "Fout", f"Kon {entry_point} niet starten:\n{e}")
            self.start_app_btn.setEnabled(True)

    def _handle_app_running(self):
        entry_point = self.entry_point_input.text().strip() or "main.py"
        self.status_label.setText(f"{entry_point} draait op de achtergrond.")
        self._log_text(f"[{datetime.now():%H:%M:%S}] {entry_point} succesvol gestart.")

    def _handle_app_crashed(self, stderr: str):
        entry_point = self.entry_point_input.text().strip() or "main.py"
        self.status_label.setText("CRASH GEDETECTEERD")
        self._log_text(f"[{datetime.now():%H:%M:%S}] CRASH DETECTIE ({entry_point}):\n{stderr}")
        QMessageBox.critical(self, "Opstartfout", f"'{entry_point}' is gecrasht bij opstarten:\n\n{stderr}")
        self.start_app_btn.setEnabled(True)

    def _handle_app_closed(self):
        entry_point = self.entry_point_input.text().strip() or "main.py"
        self.status_label.setText(f"{entry_point} is afgesloten.")
        self._log_text(f"[{datetime.now():%H:%M:%S}] {entry_point} is afgesloten.")
        self.start_app_btn.setEnabled(True)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS_STYLE)
    
    font = QFont("Segoe UI", 9)
    app.setFont(font)

    window = PythonPatchManager()
    window.show()
    sys.exit(app.exec())