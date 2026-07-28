import traceback
from PyQt6.QtWidgets import QMainWindow, QFileDialog
from PyQt6.uic import loadUi
from omegaconf import OmegaConf
from ast import literal_eval

from src.gui.utils import *


class AdvancedOptions(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        loadUi("src/gui/advanced_options.ui", self)
        self.resize(530, 450)

        # --- Internal attributes ---
        self.conf = parent.conf

        # --- Connections ---
        # self.btn_data_dest.clicked.connect(lambda: self._browse_folder(self.le_data_dest))
        # self.btn_post_dest.clicked.connect(lambda: self._browse_folder(self.le_post_dest))
        self.btn_apply.clicked.connect(self._apply_changes)
        self.btn_cancel.clicked.connect(self._cancel)

        # --- Initial state of objects ---

        # data
        # self.le_data_dest.setText(str(self.conf.data.src_res))
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
        # self.le_post_dest.setText(str(self.conf.postprocessing.src_transforms))
        self.le_absurd_dist_local.setText(str(self.conf.postprocessing.absurd_dist_local))
        self.le_absurd_dist_global.setText(str(self.conf.postprocessing.absurd_dist_global))

    def closeEvent(self, event):
        super().closeEvent(event)  # only accept/close if no error

    def _cancel(self):
        self.close()

    def _apply_changes(self):
        # Test values
        try:
            # assert test_value(self, is_a_path(self.le_data_dest.text()) or self.le_data_dest.text() == 'default', self.le_data_dest, self.scrollArea)
            if self.cb_output_transformed.isChecked():
                assert test_value(self, 
                                  (self.le_output_transformed.text() == "-1" or self.le_output_transformed.text().isnumeric()),
                                  self.le_output_transformed, self.scrollArea,
                                  )
            assert test_value(self, self.le_max_iter.text().isnumeric(), self.le_max_iter, self.scrollArea)
            assert test_value(self, will_it_float(self.le_threshold.text()), self.le_threshold, self.scrollArea)
            if is_string_list(self.le_max_correspondance.text()):
                max_corr = literal_eval(self.le_max_correspondance.text())
                assert test_value(self, len(max_corr) > 0, self.le_max_correspondance, self.scrollArea)
                for x in max_corr:
                    assert test_value(self, will_it_float(x), self.le_max_correspondance, self.scrollArea)
            else:
                assert test_value(self, will_it_float(self.le_max_correspondance.text()), self.le_max_correspondance, self.scrollArea)
            assert test_value(self, test_value(self, will_it_float(self.le_max_area.text()), self.le_max_area, self.scrollArea), self.le_max_area, self.scrollArea)
            assert test_value(self, will_it_float(self.le_ht_x.text()), self.le_ht_x, self.scrollArea)
            assert test_value(self, will_it_float(self.le_ht_y.text()), self.le_ht_y, self.scrollArea)
            assert test_value(self, will_it_float(self.le_ht_z.text()), self.le_ht_z, self.scrollArea)
            assert test_value(self, self.le_field_x.text() != "", self.le_field_x, self.scrollArea)
            assert test_value(self, self.le_field_y.text() != "", self.le_field_y, self.scrollArea)
            assert test_value(self, self.le_field_z.text() != "", self.le_field_z, self.scrollArea)
            assert test_value(self, self.le_field_classification.text() != "", self.le_field_classification, self.scrollArea)
            assert test_value(self, is_string_list(self.le_cat_to_rm.text()), self.le_cat_to_rm, self.scrollArea)
            for x in literal_eval(self.le_cat_to_rm.text()):
                assert test_value(self, isinstance(x, int), self.le_cat_to_rm, self.scrollArea)
            # assert test_value(self, is_a_path(self.le_post_dest.text()) or self.le_post_dest.text() == 'default', self.le_post_dest, self.scrollArea)
            assert test_value(self, will_it_float(self.le_absurd_dist_local.text()), self.le_absurd_dist_local, self.scrollArea)
            assert test_value(self, will_it_float(self.le_absurd_dist_local.text()), self.le_absurd_dist_local, self.scrollArea)
        except Exception:
            tb = traceback.format_exc()
            print(tb)
            return False
        
        # Update conf
        # data
        # OmegaConf.update(self.conf, 'data.src_res', self.le_data_dest.text())
        OmegaConf.update(self.conf, 'data.res_suffixe', self.le_data_suffixe.text())
        OmegaConf.update(self.conf, 'args.do_output_transformed', self.cb_output_transformed.isChecked())
        OmegaConf.update(self.conf, 'args.output_level', int(self.le_output_transformed.text()))

        # process:
        OmegaConf.update(self.conf, 'args.max_iteration', int(self.le_max_iter.text()))
        OmegaConf.update(self.conf, 'args.threshold', float(self.le_threshold.text()))
        if is_string_list(self.le_max_correspondance.text()):
            OmegaConf.update(self.conf, 'args.max_correspondence', literal_eval(self.le_max_correspondance.text()))
        else:
            OmegaConf.update(self.conf, 'args.max_correspondence', float(self.le_max_correspondance.text()))
        OmegaConf.update(self.conf, 'args.max_area', float(self.le_max_area.text()))
        OmegaConf.update(self.conf, 'args.huge_translation', [
            float(self.le_ht_x.text()), 
            float(self.le_ht_y.text()), 
            float(self.le_ht_z.text()),
            ])
        OmegaConf.update(self.conf, 'args.field_names', [
            self.le_field_x.text(),
            self.le_field_y.text(),
            self.le_field_z.text(),
            self.le_field_classification.text(),
        ])

        # categories:
        OmegaConf.update(self.conf, 'categories.list_cat_to_remove', literal_eval(self.le_cat_to_rm.text()))
        if is_string_list(self.le_cat_ground.text()):
            OmegaConf.update(self.conf, 'categories.cat_ground', literal_eval(self.le_cat_ground.text()))
        else:
            OmegaConf.update(self.conf, 'categories.cat_ground', int(self.le_cat_ground.text()))

        # post-processing:
        # OmegaConf.update(self.conf, 'postprocessing.src_transforms', self.le_post_dest.text())
        OmegaConf.update(self.conf, 'postprocessing.absurd_dist_local', float(self.le_absurd_dist_local.text()))
        OmegaConf.update(self.conf, 'postprocessing.absurd_dist_global', float(self.le_absurd_dist_global.text()))

        self.close()
    
    def _browse_folder(self, line_edit):
        path = QFileDialog.getExistingDirectory(
            self, "Select folder", ""
        )
        if path:
            line_edit.setText(path)
