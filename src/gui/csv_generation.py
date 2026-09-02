import os
from PyQt6.QtWidgets import QMainWindow, QFileDialog
from PyQt6.uic import loadUi
from PyQt6.QtCore import QTimer
from omegaconf import OmegaConf
from src.production_utils import preprocess_into_csv
from src.gui.gui_utils import *


class DotAnimator:
    def __init__(self, label, base_text="Processing", interval_ms=400):
        self.label = label
        self.base_text = base_text
        self.dots = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.setInterval(interval_ms)

    def _tick(self):
        self.dots = (self.dots + 1) % 4  # cycles 0,1,2,3 dots
        self.label.setText(self.base_text + "." * self.dots)

    def start(self, color="orange"):
        self.dots = 0
        self.label.setStyleSheet(f"color: {color};")
        self.label.setText(self.base_text)
        self.timer.start()

    def stop(self, final_text="Done!", color="green"):
        self.timer.stop()
        self.label.setStyleSheet(f"color: {color};")
        self.label.setText(final_text)


class CSVGen(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        loadUi("src/gui/csv_generation.ui", self)
        self.resize(500, 330)

        # --- Internal attributes ---
        self.conf = parent.conf

        # --- Connections ---
        self.btn_generate.clicked.connect(self._generate_csv)
        self.btn_epoch1.clicked.connect(lambda: browse_folder(self, self.le_epoch1))
        self.btn_epoch2.clicked.connect(lambda: browse_folder(self, self.le_epoch2))
        self.btn_res.clicked.connect(lambda: browse_folder(self, self.le_res))
        self.btn_csv_dest.clicked.connect(lambda: browse_folder(self, self.le_csv_dest))

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
        assert test_value(self, is_a_path(self.le_epoch1.text()) and self.le_epoch1.text() != "", self.le_epoch1)
        assert test_value(self, is_a_path(self.le_epoch2.text()) and self.le_epoch2.text() != "", self.le_epoch2)
        assert test_value(self, is_a_path(self.le_res.text()) and self.le_res.text() != "", self.le_res)
        assert test_value(self, is_a_path(self.le_csv_dest.text()) and self.le_csv_dest.text() != "", self.le_csv_dest)
        assert test_value(self, self.le_filename.text() != "", self.le_filename)
        assert test_value(self, self.le_pattern.text() != "", self.le_pattern)

        # Update conf
        OmegaConf.update(self.conf, 'preprocessing.src_folder_old', self.le_epoch1.text())
        OmegaConf.update(self.conf, 'preprocessing.src_folder_new', self.le_epoch2.text())
        OmegaConf.update(self.conf, 'preprocessing.src_res', self.le_res.text())
        csv_loc = os.path.dirname(self.le_epoch1.text()) if self.le_csv_dest.text().lower() == 'default' else self.le_csv_dest.text()
        OmegaConf.update(self.conf, 'production.src_csv', os.path.join(csv_loc, f"{self.le_filename.text()}.csv"))
        OmegaConf.update(self.conf, 'preprocessing.pattern', self.le_pattern.text())

        # Run generation
        if not hasattr(self, "dot_animator"):
            self.dot_animator = DotAnimator(self.lbl_state, base_text="Processing")
        self.dot_animator.start()
        self.worker_had_error = False

        try:
            self.worker = WorkerThread(
                preprocess_into_csv,
                self.conf.preprocessing.src_folder_old, 
                self.conf.preprocessing.src_folder_new, 
                self.conf.preprocessing.src_res,
                self.conf.production.src_csv, 
                self.conf.preprocessing.pattern, 
                verbose=True,
                )
        
            self.worker.finished.connect(self._on_worker_finished)
            self.worker.error_occurred.connect(self._on_worker_error)
            self.worker.start()
        except Exception as e:
            self.dot_animator.stop("Error!", color='red')

        self.parent().le_csv_file.setText(self.conf.production.src_csv)
    def _on_worker_finished(self):
        if not self.worker_had_error:
            self.dot_animator.stop("Done!")

    def _on_worker_error(self, traceback_str):
        self.worker_had_error = True
        self.dot_animator.stop("Error!", color='red')
        print("ERROR:\n" + traceback_str)
