import sys
import os
import traceback
from PyQt6.QtWidgets import QMainWindow, QApplication, QFileDialog, QLabel, QLineEdit, QTextEdit, QPlainTextEdit
from PyQt6.QtCore import QObject, QThread, pyqtSignal, Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.uic import loadUi
from omegaconf import OmegaConf
from process_one_tile import ICP_process
from production import production
from tkinter import messagebox


# --------------------------------
# Stream redirector
# --------------------------------
class Stream(QObject):
    text_written = pyqtSignal(str)

    def write(self, text):
        self.text_written.emit(str(text))

    def flush(self):
        pass

    def isatty(self):
        return False  # needed for tqdm to not try terminal-specific behavior


# --------------------------------
# Worker thread
# --------------------------------
class WorkerThread(QThread):
    error_occurred = pyqtSignal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            self.fn(*self.args, **self.kwargs)
        except Exception:
            tb = traceback.format_exc()
            self.error_occurred.emit(tb)


# --------------------------------
# Main UI
# --------------------------------
class mainUI(QMainWindow):
    def __init__(self):
        super(mainUI, self).__init__()
        loadUi("src/gui.ui", self)

        # --- Internal attributes ---
        self.mode = 'single'

        # --- Buttons ---
        self.btn_run_process.clicked.connect(self.run_algorithm)
        self.btn_epoch1.clicked.connect(lambda: self._browse(self.le_epoch1))
        self.btn_epoch2.clicked.connect(lambda: self._browse(self.le_epoch2))
        self.btn_csv_file.clicked.connect(lambda: self._browse(self.le_csv_file, file_types="CSV files (*.csv)"))
        self.btn_generation_csv.clicked.connect(notimplementedyet)
        self.btn_advanced.clicked.connect(notimplementedyet)
        self.btn_generation_csv.clicked.connect(notimplementedyet)

        # --- Top menus ---
        self.actionSingle.triggered.connect(self._selectSingle)
        self.actionMultiple.triggered.connect(self._selectMultiple)

        # --- Others ---
        self.cb_split.clicked.connect(self._cb_split_clicked)

        # redirect stdout to log box
        do_show_logs = True
        if do_show_logs:
            self.stream = Stream()
            self.stream.text_written.connect(self._write_log)
            sys.stdout = self.stream
            sys.stderr = self.stream

        # --- Initial state of objects ---
        conf_single = OmegaConf.load('./config/one_tile.yaml')
        conf_multiple = OmegaConf.load('./config/production.yaml')
        self.conf = OmegaConf.merge(conf_single, conf_multiple)

        self.fr_multiple.setVisible(False)

        # checkbox if split
        self.cb_split.setChecked(self.conf.categories.split_ground_anthropic)
        self._cb_split_clicked()

        # icp method
        method_id = ['pointtopoint', 'pointtoplane', 'gicp', 'mix'].index(self.conf.args.method)
        self.cb_icp_method.setCurrentIndex(method_id)
        if method_id == 3:
            # OmegaConf.update(self.conf, "categories.split_ground_anthropic", True)
            self.cb_split.setChecked(True)
            self._cb_split_clicked()

        # min sizes and num of points
        self.le_global_tile.setText(str(self.conf.categories.min_tile_size_ground))
        self.le_global_points.setText(str(self.conf.categories.min_points_ground))
        self.le_ground_tile.setText(str(self.conf.categories.min_tile_size_ground))
        self.le_ground_points.setText(str(self.conf.categories.min_points_ground))
        self.le_anthropic_tile.setText(str(self.conf.categories.min_tile_size_anthropic))
        self.le_anthropic_points.setText(str(self.conf.categories.min_points_anthropic))
        
        # outputs
        init_alignment_id = ['both', 'with', 'without'].index(self.conf.postprocessing.to_keep.initial_alignment)
        self.cbb_init_alignment.setCurrentIndex(init_alignment_id)
        self.cb_layers.setChecked(self.conf.postprocessing.to_keep.layers)
        self.cb_full_tree.setChecked(self.conf.postprocessing.to_keep.full_tree)

    def _write_log(self, text):
        self.log_box.moveCursor(QTextCursor.MoveOperation.End)
        self.log_box.insertPlainText(text)
        self.log_box.moveCursor(QTextCursor.MoveOperation.End)

    def _browse(self, line_edit, file_types="Point Clouds (*.las *.laz *.pcd *.ply)"):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select file", "",
            filter=f"{file_types};;All files (*)"
        )
        if path:
            line_edit.setText(path)

    def _selectSingle(self):
        self.fr_multiple.setVisible(False)
        self.fr_single.setVisible(True)
        self.lbl_mode.setText("Mode: Single")
        self.mode = 'single'

    def _selectMultiple(self):
        self.fr_multiple.setVisible(True)
        self.fr_single.setVisible(False)
        self.lbl_mode.setText("Mode: Multiple")
        self.mode = 'multiple'

    def run_algorithm(self):
        # Test values
        if self.mode == 'single':
            assert os.access(self.le_epoch1.text(), os.W_OK)
            assert os.access(self.le_epoch2.text(), os.W_OK)
        else:
            assert os.access(self.le_csv_file.text(), os.W_OK)
        
        if self.cb_split.isChecked():
            assert self.le_ground_tile.text().isnumeric()
            assert self.le_ground_points.text().isnumeric()
            assert self.le_anthropic_tile.text().isnumeric()
            assert self.le_anthropic_points.text().isnumeric()
        else:
            assert self.le_global_tile.text().isnumeric()
            assert self.le_global_points.text().isnumeric()

        # Update conf
        OmegaConf.update(self.conf, 'data.src_pc1', self.le_epoch1.text())
        OmegaConf.update(self.conf, 'data.src_pc2', self.le_epoch2.text())
        OmegaConf.update(self.conf, 'production.src_csv', self.le_csv_file.text())
        OmegaConf.update(self.conf, 'categories.split_ground_anthropic', self.cb_split.isChecked())
        if self.cb_split.isChecked():
            OmegaConf.update(self.conf, 'categories.min_tile_size_ground', int(self.le_ground_tile.text()))
            OmegaConf.update(self.conf, 'categories.min_points_ground', int(self.le_ground_points.text()))
            OmegaConf.update(self.conf, 'categories.min_tile_size_anthropic', int(self.le_anthropic_tile.text()))
            OmegaConf.update(self.conf, 'categories.min_points_anthropic', int(self.le_anthropic_points.text()))
        else:
            OmegaConf.update(self.conf, 'categories.min_tile_size_ground', int(self.le_global_tile.text()))
            OmegaConf.update(self.conf, 'categories.min_points_ground', int(self.le_global_points.text()))
        OmegaConf.update(self.conf, 'postprocessing.to_keep.initial_alignment', self.cbb_init_alignment.currentText())
        OmegaConf.update(self.conf, 'postprocessing.to_keep.layers', self.cb_layers.isChecked())
        OmegaConf.update(self.conf, 'postprocessing.to_keep.full_tree', self.cb_full_tree.isChecked())

        self.btn_run_process.setEnabled(False)
        if self.mode == 'single':
            self.worker = WorkerThread(ICP_process, self.conf, self.conf.args.verbose)
        else:
            self.worker = WorkerThread(production, self.conf, True)
        self.worker.finished.connect(lambda: self.btn_run_process.setEnabled(True))
        self.worker.error_occurred.connect(self._on_worker_error)
        self.worker.start()

    def _on_worker_error(self, traceback_str):
        print("\n" + "="*50)
        print("ERROR OCCURRED:")
        print(traceback_str)
        print("="*50 + "\n")

    def closeEvent(self, event):
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        super().closeEvent(event)

    def _cb_split_clicked(self):
        print(self.cb_split.isChecked())
        self._set_frame_disabled_look(self.fr_global_limits, self.cb_split.isChecked())
        self._set_frame_disabled_look(self.fr_ground_limits, not self.cb_split.isChecked())
        self._set_frame_disabled_look(self.fr_anthropic_limits, not self.cb_split.isChecked())

    def _set_frame_disabled_look(self, frame, disabled: bool):
        """
        Recursively greys out QLabel and makes QLineEdit/QTextEdit/QPlainTextEdit
        read-only with a grey background, to visually + functionally disable a section.
        """
        labels = frame.findChildren(QLabel)
        text_edits = frame.findChildren((QLineEdit, QTextEdit, QPlainTextEdit))
        for label in labels:
            if disabled:
                label.setStyleSheet("color: grey;")
            else:
                label.setStyleSheet("")  # reset to default/theme style

        for edit in text_edits:
            edit.setReadOnly(disabled)
            if disabled:
                edit.setStyleSheet("background-color: #e0e0e0; color: grey;")
            else:
                edit.setStyleSheet("")

    def test(self):
        print(self.cb_split.isChecked())


def notimplementedyet():
    messagebox.showwarning("Warning", "Not implemented yet!") 


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ui = mainUI()
    ui.show()
    app.exec()
    