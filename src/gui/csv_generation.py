import sys
import os
import traceback
from PyQt6.QtWidgets import QMainWindow, QApplication, QFileDialog, QLabel, QLineEdit, QTextEdit, QPlainTextEdit
from PyQt6.QtCore import QObject, QThread, pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QTextCursor
from PyQt6.uic import loadUi
from omegaconf import OmegaConf
from tkinter import messagebox
from ast import literal_eval
import traceback as tb
from pathvalidate import sanitize_filepath

from src.production_utils import preprocess_into_csv
from src.gui.utils import *

class CSVGen(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        loadUi("src/gui/csv_generation.ui", self)
        self.resize(500, 330)

        # --- Internal attributes ---
        self.conf = parent.conf

        # --- Connections ---
        self.btn_generate.clicked.connect(self._generate_csv)
        self.btn_epoch1.clicked.connect(lambda: self._browse_folder(self.le_epoch1))
        self.btn_epoch2.clicked.connect(lambda: self._browse_folder(self.le_epoch2))
        self.btn_res.clicked.connect(lambda: self._browse_folder(self.le_res))
        self.btn_csv_dest.clicked.connect(lambda: self._browse_folder(self.le_csv_dest))

        # # --- Initial state of objects ---
        self.le_epoch1.setText(str(self.conf.preprocessing.src_folder_old))
        self.le_epoch2.setText(str(self.conf.preprocessing.src_folder_new))
        self.le_res.setText(self.conf.preprocessing.src_res)
          
        if is_a_path(self.conf.production.src_csv):
            if os.path.splitext(self.conf.production.src_csv)[1] == "":
                self.le_csv_dest.setText(str(self.conf.production.src_csv))
            else:
                csv_filename = os.path.basename(self.conf.production.src_csv)
                csv_dest = os.path.dirname(self.conf.production.src_csv)
                self.le_csv_dest.setText(csv_dest)
                if csv_filename.endswith('.csv'):
                    self.le_filename.setText(csv_filename.split('.')[0])

        self.le_pattern.setText(self.conf.preprocessing.pattern)

    def _generate_csv(self):
        # Test values
        assert is_a_path(self.le_epoch1.text()) and self.le_epoch1.text() != ""
        assert is_a_path(self.le_epoch2.text()) and self.le_epoch2.text() != ""
        assert is_a_path(self.le_res.text()) and self.le_res.text() != ""
        assert is_a_path(self.le_csv_dest.text()) and self.le_csv_dest.text() != ""
        assert self.le_filename.text() != ""
        assert self.le_pattern.text() != ""

        # Update conf
        OmegaConf.update(self.conf, 'preprocessing.src_folder_old', self.le_epoch1.text())
        OmegaConf.update(self.conf, 'preprocessing.src_folder_new', self.le_epoch2.text())
        OmegaConf.update(self.conf, 'preprocessing.src_res', self.le_res.text())
        OmegaConf.update(self.conf, 'production.src_csv', os.path.join(self.le_csv_dest.text(), self.le_filename.text()))
        OmegaConf.update(self.conf, 'preprocessing.pattern', self.le_pattern.text())

        # Run generation
        preprocess_into_csv(
            self.conf.preprocessing.src_folder_old, 
            self.conf.preprocessing.src_folder_new, 
            self.conf.preprocessing.src_res,
            self.conf.production.src_csv, 
            self.conf.preprocessing.pattern, 
            verbose=True,
            )

        self.parent().le_csv_file.setText(self.conf.production.src_csv)

    def _browse_folder(self, line_edit):
        path = QFileDialog.getExistingDirectory(
            self, "Select folder", ""
        )
        if path:
            line_edit.setText(path)

