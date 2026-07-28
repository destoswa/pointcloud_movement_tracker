import sys
import os
import traceback
from PyQt6.QtWidgets import QMainWindow, QApplication, QFileDialog, QLabel, QLineEdit, QTextEdit, QPlainTextEdit
from PyQt6.QtGui import QTextCursor
from PyQt6.uic import loadUi
from omegaconf import OmegaConf

from process_one_tile import ICP_process
from production import production
from src.gui.utils import *
from src.gui.csv_generation import CSVGen
from src.gui.advanced_options import AdvancedOptions


# --------------------------------
# Main UI
# --------------------------------
class mainUI(QMainWindow):
    def __init__(self):
        super(mainUI, self).__init__()
        loadUi("src/gui/main.ui", self)
        self.resize(650, 850)

        # --- Internal attributes ---
        self.mode = 'single'

        # --- Connections ---
        # buttons
        self.btn_run_process.clicked.connect(self._run_algorithm)
        self.btn_epoch1.clicked.connect(lambda: self._browse(self.le_epoch1))
        self.btn_epoch2.clicked.connect(lambda: self._browse(self.le_epoch2))
        self.btn_res_dest.clicked.connect(lambda: self._browse_folder(self.le_res_dest))
        self.btn_csv_file.clicked.connect(lambda: self._browse(self.le_csv_file, file_types="CSV files (*.csv)"))
        self.btn_advanced.clicked.connect(self._open_advanced_options_form)
        self.btn_generation_csv.clicked.connect(self._open_csv_gen_form)
        self.btn_clear_logs.clicked.connect(self._clear_logs)

        # top menus 
        self.actionSingle.triggered.connect(lambda: self._select_mode('Single file', 'single', self.page_single))
        self.actionMultiple.triggered.connect(lambda: self._select_mode('Multiple files', 'multiple', self.page_multiple))
        self.actionPostprocessing.triggered.connect(lambda: self._select_mode('Postprocessing on existing quadtree', 'postprocessing', self.page_postprocessing))
        # self.menu_advanced_options.triggered.connect(self._open_advanced_options_form)

        # others
        self.cb_split.clicked.connect(self._cb_split_clicked)
        self.cbb_icp_method.currentTextChanged.connect(self._change_icp_method)

        # --- Initial state of objects ---
        conf_single = OmegaConf.load('./config/one_tile.yaml')
        conf_multiple = OmegaConf.load('./config/production.yaml')
        self.conf = OmegaConf.merge(conf_single, conf_multiple)

        self._select_mode('Single file', 'single', self.page_single)

        # inputs
        self.le_epoch1.setText(str(self.conf.data.src_pc1))
        self.le_epoch2.setText(str(self.conf.data.src_pc2))
        self.le_res_dest.setText(str(self.conf.data.src_res))
        self.le_prefix.setText(str(self.conf.data.res_prefix))
        self.le_csv_file.setText(str(self.conf.production.src_csv))
        self.le_post_prefix.setText(str(self.conf.data.res_prefix))
        self.le_post_pickle.setText(os.path.join(os.path.dirname(self.conf.data.src_pc1), f'{self.conf.data.res_prefix}_pyramid_transforms.pickle'))

        # checkbox if split
        self.cb_split.setChecked(self.conf.categories.split_ground_anthropic)
        self._cb_split_clicked()

        # icp method
        method_id = ['pointtopoint', 'pointtoplane', 'gicp', 'mix'].index(self.conf.args.method)
        self.cbb_icp_method.setCurrentIndex(method_id)
        if method_id == 3:  # if mix
            self.cb_split.setChecked(True)
            self.cb_split.setDisabled(True)
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

        # redirect stdout to log box
        do_show_logs = True
        if do_show_logs:
            self.stream = Stream()
            self.stream.text_written.connect(self._write_log)
            sys.stdout = self.stream
            sys.stderr = self.stream

    def _test_value(self, test_res, object, scrollArea=None) -> bool:
        if test_res:
            return True
        else:
            self.blink_timer = Blinker(object, color_on="red", interval_ms=300, duration_ms=3000)
            self.blink_timer.start()
            if scrollArea != None:
                scrollArea.ensureWidgetVisible(object, xMargin=10, yMargin=10)

            return False
    
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

    def _browse_folder(self, line_edit):
        path = QFileDialog.getExistingDirectory(
            self, "Select folder", ""
        )
        if path:
            line_edit.setText(path)    

    def _select_mode(self, text, mode, page):
        self.lbl_mode.setText(text)
        self.mode = mode
        self.stackedWidget.setCurrentWidget(page)

        # Hide some options when postprocessing
        if mode == 'postprocessing':
            self.fr_options.setEnabled(False)
            self.btn_advanced.setEnabled(True)
        else:
            self.fr_options.setEnabled(True)

    def _change_icp_method(self):
        if self.cbb_icp_method.currentText() == 'mix':
            self.cb_split.setChecked(True)
            self.cb_split.setDisabled(True)
            self._cb_split_clicked()
        else:
            self.cb_split.setDisabled(False)
    
    def _open_csv_gen_form(self):
        csv_gen_form = CSVGen(self)
        main_pos = self.pos()
        csv_gen_form.move(main_pos.x() - 300, main_pos.y() - 100)
        csv_gen_form.show()

    def _open_advanced_options_form(self):
        advanced_form = AdvancedOptions(self)
        # Position relative to main window's top-left corner
        main_pos = self.pos()
        advanced_form.move(main_pos.x() + 500, main_pos.y() - 100)
        advanced_form.show()

    def _clear_logs(self):
        self.log_box.setText('')

    def _run_algorithm(self):
        # Test values
        try:
            if self.mode == 'single':
                assert test_value(self, os.access(self.le_epoch1.text(), os.W_OK), self.le_epoch1)
                assert test_value(self, os.access(self.le_epoch2.text(), os.W_OK), self.le_epoch2)
            else:
                assert test_value(self, os.access(self.le_csv_file.text(), os.W_OK), self.le_csv_file)
            
            if self.cb_split.isChecked():
                assert test_value(self, will_it_float(self.le_ground_tile.text()), self.le_ground_tile)
                assert test_value(self, self.le_ground_points.text().isnumeric(), self.le_ground_points)
                assert test_value(self, will_it_float(self.le_anthropic_tile.text()), self.le_anthropic_tile)
                assert test_value(self, self.le_anthropic_points.text().isnumeric(), self.le_anthropic_points)
            else:
                assert test_value(self, will_it_float(self.le_global_tile.text()), self.le_global_tile)
                assert test_value(self, self.le_global_points.text().isnumeric(), self.le_global_points)
        except Exception:
            tb = traceback.format_exc()
            print(tb)
            return
        
        # Update conf
        OmegaConf.update(self.conf, 'data.src_pc1', self.le_epoch1.text())
        OmegaConf.update(self.conf, 'data.src_pc2', self.le_epoch2.text())
        OmegaConf.update(self.conf, 'production.src_csv', self.le_csv_file.text())
        OmegaConf.update(self.conf, 'args.method', ['pointtopoint', 'pointtoplane', 'gicp', 'mix'][self.cbb_icp_method.currentIndex()])
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
            OmegaConf.update(self.conf, 'preprocessing.do_preprocessing', False)
            self.worker = WorkerThread(production, self.conf, self.conf, True)
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

    def test(self, msg='derp'):
        print(f"test: {msg}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ui = mainUI()
    ui.show()
    app.exec()
    