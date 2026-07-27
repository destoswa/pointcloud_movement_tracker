import sys
import os
import traceback
from PyQt6.QtWidgets import QMainWindow, QApplication, QFileDialog, QLabel, QLineEdit, QTextEdit, QPlainTextEdit
from PyQt6.QtCore import QObject, QThread, pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QTextCursor
from PyQt6.uic import loadUi
from omegaconf import OmegaConf
from process_one_tile import ICP_process
from production import production
from tkinter import messagebox
from ast import literal_eval
import traceback as tb


def will_it_float(element: any) -> bool:
    #If you expect None to be passed:
    if element is None: 
        return False
    try:
        float(element)
        return True
    except ValueError:
        return False


def is_string_list(text: str) -> bool:
    try:
        result = literal_eval(text)
        return isinstance(result, list)
    except (ValueError, SyntaxError):
        return False

    
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
# Blinker
# --------------------------------
class Blinker(QObject):
    def __init__(self, widget, color_on="red", color_off="", 
                 interval_ms=300, duration_ms=3000, parent=None):
        super().__init__(parent)
        self.widget = widget
        self.color_on = color_on
        self.color_off = color_off
        self.state = False

        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self._toggle)
        self.blink_timer.setInterval(interval_ms)

        self.stop_timer = QTimer(self)
        self.stop_timer.setSingleShot(True)
        self.stop_timer.timeout.connect(self.stop)
        self.stop_timer.setInterval(duration_ms)

    def _toggle(self):
        self.state = not self.state
        self._apply_style()

    def _apply_style(self):
        style = f"border: 2px solid {self.color_on};" if self.state else self.color_off
        self.widget.setStyleSheet(style)

    def start(self):
        self.state = False
        self.blink_timer.start()
        self.stop_timer.start()

    def stop(self):
        self.blink_timer.stop()
        self.state = False
        self._apply_style()  # ensure it ends in the "off" state

# --------------------------------
# Main UI
# --------------------------------
class mainUI(QMainWindow):
    def __init__(self):
        super(mainUI, self).__init__()
        loadUi("src/gui/main.ui", self)

        # --- Internal attributes ---
        self.mode = 'single'

        # --- Connections ---
        # buttons
        self.btn_run_process.clicked.connect(self._run_algorithm)
        self.btn_epoch1.clicked.connect(lambda: self._browse(self.le_epoch1))
        self.btn_epoch2.clicked.connect(lambda: self._browse(self.le_epoch2))
        self.btn_csv_file.clicked.connect(lambda: self._browse(self.le_csv_file, file_types="CSV files (*.csv)"))
        self.btn_advanced.clicked.connect(self._open_advanced_options_form)
        self.btn_generation_csv.clicked.connect(self._open_csv_gen_form)

        # top menus 
        self.actionSingle.triggered.connect(self._selectSingle)
        self.actionMultiple.triggered.connect(self._selectMultiple)

        # others
        self.cb_split.clicked.connect(self._cb_split_clicked)
        self.cbb_icp_method.currentTextChanged.connect(self._change_icp_method)


        # --- Initial state of objects ---
        conf_single = OmegaConf.load('./config/one_tile.yaml')
        conf_multiple = OmegaConf.load('./config/production.yaml')
        self.conf = OmegaConf.merge(conf_single, conf_multiple)

        self.fr_multiple.setVisible(False)

        # inputs
        self.le_epoch1.setText(str(self.conf.data.src_pc1))
        self.le_epoch2.setText(str(self.conf.data.src_pc2))
        self.le_csv_file.setText(str(self.conf.production.src_csv))

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

    def _change_icp_method(self):
        if self.cbb_icp_method.currentText() == 'mix':
            self.cb_split.setChecked(True)
            self.cb_split.setDisabled(True)
            self._cb_split_clicked()
        else:
            self.cb_split.setDisabled(False)
    
    def _open_csv_gen_form(self):
        csv_gen_form = CSVGen(self)
        csv_gen_form.show()

    def _open_advanced_options_form(self):
        advanced_form = AdvancedOptions(self)
        # Position relative to main window's top-left corner
        main_pos = self.pos()
        advanced_form.move(main_pos.x() + 500, main_pos.y() - 100)
        advanced_form.show()

    def _run_algorithm(self):
        # Test values
        if self.mode == 'single':
            assert os.access(self.le_epoch1.text(), os.W_OK)
            assert os.access(self.le_epoch2.text(), os.W_OK)
        else:
            assert os.access(self.le_csv_file.text(), os.W_OK)
        
        if self.cb_split.isChecked():
            assert will_it_float(self.le_ground_tile.text())
            assert self.le_ground_points.text().isnumeric()
            assert will_it_float(self.le_anthropic_tile.text())
            assert self.le_anthropic_points.text().isnumeric()
        else:
            assert will_it_float(self.le_global_tile.text())
            assert self.le_global_points.text().isnumeric()

        # Update conf
        OmegaConf.update(self.conf, 'data.src_pc1', self.le_epoch1.text())
        OmegaConf.update(self.conf, 'data.src_pc2', self.le_epoch2.text())
        OmegaConf.update(self.conf, 'production.src_csv', self.le_csv_file.text())
        OmegaConf.update(self.conf, 'args.method', self.cbb_icp_method.currentText())
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


class CSVGen(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        loadUi("src/gui/csv_generation.ui", self)

        # --- Internal attributes ---
        self.conf = parent.conf


class AdvancedOptions(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        loadUi("src/gui/advanced_options.ui", self)

        # --- Internal attributes ---
        self.conf = parent.conf

        # --- Connections ---
        self.btn_data_dest.clicked.connect(lambda: self._browse_folder(self.le_data_dest))
        self.btn_post_dest.clicked.connect(lambda: self._browse_folder(self.le_post_dest))

        # --- Initial state of objects ---

        # data
        self.le_data_dest.setText(str(self.conf.data.src_res))
        self.le_data_suffixe.setText(str(self.conf.data.res_suffixe))
        self.cb_output_transformed.setChecked(self.conf.args.do_output_transformed)
        self.le_output_transformed.setText(str(self.conf.args.output_level))

        # process:
        self.le_max_iter.setText(str(self.conf.args.max_iteration))
        self.le_threshold.setText(str(self.conf.args.threshold))
        self.le_max_correspondance.setText(str(self.conf.args.max_correspondence))
        self.le_max_area.setText(str(self.conf.args.max_area))
        self.le_ht_x.setText(str(self.conf.args.huge_translation[0]))
        self.le_ht_y.setText(str(self.conf.args.huge_translation[1]))
        self.le_ht_z.setText(str(self.conf.args.huge_translation[2]))
        self.le_field_x.setText(str(self.conf.args.field_names[0]))
        self.le_field_y.setText(str(self.conf.args.field_names[1]))
        self.le_field_z.setText(str(self.conf.args.field_names[2]))
        self.le_field_classification.setText(str(self.conf.args.field_names[3]))

        # categories:
        self.le_cat_to_rm.setText(str(self.conf.categories.list_cat_to_remove))
        self.le_cat_ground.setText(str(self.conf.categories.cat_ground))

        # post-processing:
        self.le_post_dest.setText(str(self.conf.postprocessing.src_transforms))
        self.le_absurd_dist_local.setText(str(self.conf.postprocessing.absurd_dist_local))
        self.le_absurd_dist_global.setText(str(self.conf.postprocessing.absurd_dist_global))

    def closeEvent(self, event):
        try:
            self._apply_changes()
            super().closeEvent(event)  # only accept/close if no error
        except Exception:
            tb = traceback.format_exc()
            parent = self.parent()
            if parent is not None and hasattr(parent, "log_box"):
                parent.log_box.insertPlainText(tb)
                self.blink_timer = Blinker(parent.log_box, color_on="red", interval_ms=300, duration_ms=3000)
                self.blink_timer.start()
            else:
                print(tb)
            event.ignore()  # keep the window open

    def _apply_changes(self):
        # Test values
        assert os.access(self.le_data_dest.text(), os.W_OK) or self.le_data_dest.text() == 'default'
        if self.cb_output_transformed.isChecked():
            assert self.le_output_transformed.text().isnumeric() or int(self.le_output_transformed.text()) == -1
        assert self.le_max_iter.text().isnumeric()
        assert will_it_float(self.le_threshold.text())
        if is_string_list(self.le_max_correspondance.text()):
            max_corr = literal_eval(self.le_max_correspondance.text())
            assert len(max_corr) > 0
            for x in max_corr:
                assert will_it_float(x)
        else:
            assert will_it_float(self.le_max_correspondance.text())
        assert will_it_float(self.le_max_area.text())
        assert will_it_float(self.le_ht_x.text())
        assert will_it_float(self.le_ht_y.text())
        assert will_it_float(self.le_ht_z.text())
        assert self.le_field_x.text() != ""
        assert self.le_field_y.text() != ""
        assert self.le_field_z.text() != ""
        assert self.le_field_classification.text() != ""
        assert is_string_list(self.le_cat_to_rm.text())
        for x in literal_eval(self.le_cat_to_rm.text()):
            assert isinstance(x, int)
        assert os.access(self.le_post_dest.text(), os.W_OK) or self.le_post_dest.text() == 'default'
        assert will_it_float(self.le_absurd_dist_local.text())
        assert will_it_float(self.le_absurd_dist_local.text())

        # Update conf
        # data
        self.conf.data.src_res = self.le_data_dest.text()
        self.conf.data.res_suffixe = self.le_data_suffixe.text()
        self.conf.args.do_output_transformed = self.cb_output_transformed.isChecked()
        self.conf.args.output_level = int(self.le_output_transformed.text())

        # process:
        self.conf.args.max_iteration = int(self.le_max_iter.text())
        self.conf.args.threshold = float(self.le_threshold.text())
        if is_string_list(self.le_max_correspondance.text()):
            self.conf.args.max_correspondence = literal_eval(self.le_max_correspondance.text())
        else:
            self.conf.args.max_correspondence = float(self.le_max_correspondance.text())
        self.conf.args.max_area = float(self.le_max_area.text())
        self.conf.args.huge_translation = [
            float(self.le_ht_x.text()), 
            float(self.le_ht_y.text()), 
            float(self.le_ht_z.text()),
            ]
        self.conf.args.field_names = [
            self.le_field_x.text(),
            self.le_field_y.text(),
            self.le_field_z.text(),
            self.le_field_classification.text(),
        ]

        # categories:
        self.conf.categories.list_cat_to_remove = literal_eval(self.le_cat_to_rm.text())
        if is_string_list(self.le_cat_ground.text()):
            self.conf.categories.cat_ground = literal_eval(self.le_cat_ground.text())
        else:
            self.conf.categories.cat_ground = int(self.le_cat_ground.text())

        # post-processing:
        self.conf.postprocessing.src_transforms = self.le_post_dest.text()
        self.conf.postprocessing.absurd_dist_local = float(self.le_absurd_dist_local.text())
        self.conf.postprocessing.absurd_dist_global = float(self.le_absurd_dist_global.text())

    def _browse_folder(self, line_edit):
        path = QFileDialog.getExistingDirectory(
            self, "Select folder", ""
        )
        if path:
            line_edit.setText(path)


def notimplementedyet():
    messagebox.showwarning("Warning", "Not implemented yet!") 


if __name__ == "__main__":
    # a = "[1,2,3]"
    # print(is_string_list(a))
    app = QApplication(sys.argv)
    ui = mainUI()
    ui.show()
    app.exec()
    