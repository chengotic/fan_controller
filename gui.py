import sys
import json
from pathlib import Path
import subprocess
import os
from PyQt6.QtCore import Qt, QPointF, QTimer
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton,
    QGridLayout, QComboBox, QListWidget, QListWidgetItem, QTabWidget, QScrollArea, QLineEdit,
    QStatusBar, QSpinBox, QCheckBox
)
from PyQt6.QtGui import QStandardItem, QStandardItemModel
import pyqtgraph as pg


CONFIG_PATH = Path(__file__).parent / "config.json"
STATUS_PATH = Path(__file__).parent / ".fan_controller_status.json"
HWMON_PATH = "/sys/class/hwmon"

class FanCurvePlot(pg.PlotWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLimits(xMin=0, xMax=100, yMin=0, yMax=100)
        self.getPlotItem().vb.setXRange(0, 100, padding=0)
        self.getPlotItem().vb.setYRange(0, 100, padding=0)
        self.setLabel('bottom', 'Temperature', '°C')
        self.setLabel('left', 'Fan Speed', '%')
        self.showGrid(x=True, y=True)
        self.curve = self.plot(pen='y', symbol='o', symbolBrush='r')
        self.points = []
        self.dragged_point = None
        self.getPlotItem().vb.setMouseEnabled(x=False, y=False)

    def set_points(self, points):
        self.points = sorted([[float(p[0]), float(p[1])] for p in points])
        x_coords = [p[0] for p in self.points]
        y_coords = [p[1] for p in self.points]
        self.curve.setData(x_coords, y_coords)

    def mousePressEvent(self, ev):
        pos = self.getPlotItem().vb.mapSceneToView(QPointF(ev.pos()))
        x, y = pos.x(), pos.y()

        closest_point = None
        min_dist = float('inf')
        for i, p in enumerate(self.points):
            dist = (p[0] - x)**2 + (p[1] - y)**2
            if dist < min_dist:
                min_dist = dist
                closest_point = i

        if ev.button() == Qt.MouseButton.LeftButton:
            if closest_point is not None and min_dist < 25:
                self.dragged_point = closest_point
            else:
                if 0 <= x <= 100 and 0 <= y <= 100:
                    self.points.append([x, y])
                    self.set_points(self.points)
                    self.dragged_point = len(self.points) - 1

        elif ev.button() == Qt.MouseButton.RightButton:
            if closest_point is not None and min_dist < 25:
                self.points.pop(closest_point)
                self.set_points(self.points)

    def mouseMoveEvent(self, ev):
        if self.dragged_point is not None:
            pos = self.getPlotItem().vb.mapSceneToView(QPointF(ev.pos()))
            x, y = pos.x(), pos.y()
            x = max(0, min(100, x))
            y = max(0, min(100, y))
            self.points[self.dragged_point] = [x, y]
            self.set_points(self.points)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.dragged_point = None
            self.set_points(self.points)

class FanControlApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fan Control")

        self.tabs = QTabWidget()
        self.hardware_tab = QWidget()
        self.curves_tab = QWidget()
        self.aliases_tab = QWidget()

        self.tabs.addTab(self.hardware_tab, "Hardware")
        self.tabs.addTab(self.curves_tab, "Curves")
        self.tabs.addTab(self.aliases_tab, "Aliases")

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tabs)
        self.status_bar = QStatusBar()
        main_layout.addWidget(self.status_bar)
        self.setLayout(main_layout)

        self.load_config()
        self.controller_process = None
        self.sensors = self.find_sensors()
        self.sensor_items = {}

        self.init_aliases_tab()
        self.init_hardware_tab()
        self.init_curves_tab()
        self.update_ui_with_aliases()


        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(1000) # Update every second

        self.restart_controller()

    def get_alias(self, path):
        return self.config.get("aliases", {}).get(path, path)

    def update_ui_with_aliases(self):
        # Update aliases tab
        for path, widgets in self.alias_widgets.items():
            widgets["alias_input"].setText(self.get_alias(path))
            if widgets["type"] == "fan":
                widgets["visible_checkbox"].setChecked(path not in self.config.get("hidden_fans", []))
            elif widgets["type"] == "sensor":
                widgets["visible_checkbox"].setChecked(path not in self.config.get("hidden_sensors", []))

        # Re-init tabs to update labels and combos
        self.sensors = self.find_sensors()
        self.init_hardware_tab()
        self.init_curves_tab()
        self.update_fan_curve_combos()

    def update_sensor_combo(self, status_data):
        for sensor_path, item in self.sensor_items.items():
            temp = status_data.get("sensors", {}).get(sensor_path)
            display_text = self.get_alias(sensor_path)
            if temp is not None:
                display_text += f" ({temp:.1f}°C)"
            item.setText(display_text)

    def init_hardware_tab(self):
        # Clear existing widgets
        if self.hardware_tab.layout() is not None:
            while self.hardware_tab.layout().count():
                item = self.hardware_tab.layout().takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
        else:
            self.hardware_tab.setLayout(QVBoxLayout())

        scroll = QScrollArea()
        self.hardware_tab.layout().addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        layout = QGridLayout(content)
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)

        self.fan_widgets = {}
        fans = self.find_fans()
        i = 0
        for fan_name, fan_path in fans.items():
            label_text = self.get_alias(fan_path) if self.get_alias(fan_path) else fan_name
            label = QLabel(label_text)
            combo = QComboBox()
            temp_label = QLabel("Temp: --°C")
            speed_label = QLabel("Speed: --%")
            
            layout.addWidget(label, i, 0)
            layout.addWidget(combo, i, 1)
            
            widgets = {
                "label": label,
                "combo": combo,
                "temp_label": temp_label,
                "speed_label": speed_label,
            }

            if fan_path == "nvidia-settings":
                min_speed_label = QLabel("Min Speed:")
                min_speed_spinbox = QSpinBox()
                min_speed_spinbox.setRange(0, 100)
                min_speed_spinbox.setValue(self.config.get("hardware", {}).get("nvidia_min_fan_speed", 26))
                layout.addWidget(min_speed_label, i, 4)
                layout.addWidget(min_speed_spinbox, i, 5)
                widgets["min_speed_spinbox"] = min_speed_spinbox

            layout.addWidget(temp_label, i, 2)
            layout.addWidget(speed_label, i, 3)

            self.fan_widgets[fan_path] = widgets
            i += 1

        layout.setRowStretch(i, 1)
        layout.setColumnStretch(6, 1)

        self.hardware_save_button = QPushButton("Save Hardware Config")
        self.hardware_save_button.clicked.connect(self.save_config)
        layout.addWidget(self.hardware_save_button, i + 1, 0, 1, 2)

    def init_curves_tab(self):
        # Clear existing widgets if they exist
        if self.curves_tab.layout() is not None:
            while self.curves_tab.layout().count():
                item = self.curves_tab.layout().takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
        else:
            self.curves_tab.setLayout(QHBoxLayout())
        
        layout = self.curves_tab.layout()

        self.curve_list = QListWidget()
        self.curve_list.currentItemChanged.connect(self.display_curve)
        layout.addWidget(self.curve_list, 1)

        scroll = QScrollArea()
        layout.addWidget(scroll, 3)
        content = QWidget()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        curve_editor_layout = QVBoxLayout(content)

        self.curve_plot = FanCurvePlot()
        curve_editor_layout.addWidget(self.curve_plot)

        curve_name_layout = QHBoxLayout()
        curve_editor_layout.addLayout(curve_name_layout)
        curve_name_layout.addWidget(QLabel("Curve Name:"))
        self.curve_name_input = QLineEdit()
        curve_name_layout.addWidget(self.curve_name_input)

        sensor_layout = QHBoxLayout()
        curve_editor_layout.addLayout(sensor_layout)
        sensor_layout.addWidget(QLabel("Sensor:"))
        self.sensor_combo = QComboBox()
        self.sensor_combo_model = QStandardItemModel()
        self.sensor_combo.setModel(self.sensor_combo_model)
        sensor_layout.addWidget(self.sensor_combo)

        # Initial population of the sensor combo model
        self.sensor_items = {}
        for sensor_name, sensor_path in self.sensors.items():
            item = QStandardItem()
            item.setData(sensor_path, Qt.ItemDataRole.UserRole)
            self.sensor_items[sensor_path] = item
            self.sensor_combo_model.appendRow(item)

        button_layout = QHBoxLayout()
        curve_editor_layout.addLayout(button_layout)
        self.new_curve_button = QPushButton("New Curve")
        self.new_curve_button.clicked.connect(self.new_curve)
        self.save_curve_button = QPushButton("Save Curve")
        self.save_curve_button.clicked.connect(self.save_curve)
        self.delete_curve_button = QPushButton("Delete Curve")
        self.delete_curve_button.clicked.connect(self.delete_curve)
        button_layout.addWidget(self.new_curve_button)
        button_layout.addWidget(self.save_curve_button)
        button_layout.addWidget(self.delete_curve_button)
        
        self.curve_list.clear()
        for curve_name in self.config.get("curves", {}):
            self.curve_list.addItem(curve_name)
    
    def find_fans_for_alias_tab(self):
        fans = {}
        # Find hwmon fans
        for path in Path(HWMON_PATH).glob("hwmon*/pwm[0-9]*"):
            if "_" in path.name:
                continue
            name = self.get_alias(str(path))
            fans[name] = str(path)

        # Add GPU fan
        gpu_fan_path = "nvidia-settings"
        fans[self.get_alias(gpu_fan_path)] = gpu_fan_path
        return fans

    def find_fans(self):
        fans = {}
        all_fans = self.find_fans_for_alias_tab()
        for name, path in all_fans.items():
            if path not in self.config.get("hidden_fans", []):
                fans[name] = path
        return fans

    def find_sensors(self):
        sensors = {}
        all_sensors = self.find_sensors_for_alias_tab()
        for name, path in all_sensors.items():
            if path not in self.config.get("hidden_sensors", []):
                sensors[name] = path
        return sensors

    def find_sensors_for_alias_tab(self):
        sensors = {}
        # Find hwmon sensors
        for path in Path(HWMON_PATH).glob("hwmon*/temp*_input"):
            sensors[str(path)] = str(path)

        # Add GPU sensor
        gpu_sensor_path = "nvidia-smi"
        sensors[gpu_sensor_path] = gpu_sensor_path
        return sensors

    def init_aliases_tab(self):
        if self.aliases_tab.layout() is not None:
            while self.aliases_tab.layout().count():
                item = self.aliases_tab.layout().takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
        else:
            self.aliases_tab.setLayout(QVBoxLayout())

        scroll = QScrollArea()
        self.aliases_tab.layout().addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        layout = QGridLayout(content)
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)

        self.alias_widgets = {}
        fans = self.find_fans_for_alias_tab()
        sensors = self.find_sensors_for_alias_tab()

        layout.addWidget(QLabel("Device Path"), 0, 0)
        layout.addWidget(QLabel("Alias"), 0, 1)
        layout.addWidget(QLabel("Visible"), 0, 2)
        
        i=1
        for path in fans.values():
            path_label = QLabel(path)
            alias_input = QLineEdit()
            visible_checkbox = QCheckBox()
            visible_checkbox.setChecked(path not in self.config.get("hidden_fans", []))

            layout.addWidget(path_label, i, 0)
            layout.addWidget(alias_input, i, 1)
            layout.addWidget(visible_checkbox, i, 2)
            self.alias_widgets[path] = {
                "alias_input": alias_input,
                "visible_checkbox": visible_checkbox,
                "type": "fan"
            }
            i+=1

        for path in sensors.values():
            path_label = QLabel(path)
            alias_input = QLineEdit()
            visible_checkbox = QCheckBox()
            visible_checkbox.setChecked(path not in self.config.get("hidden_sensors", []))

            layout.addWidget(path_label, i, 0)
            layout.addWidget(alias_input, i, 1)
            layout.addWidget(visible_checkbox, i, 2)
            self.alias_widgets[path] = {
                "alias_input": alias_input,
                "visible_checkbox": visible_checkbox,
                "type": "sensor"
            }
            i+=1

        self.save_aliases_button = QPushButton("Save Aliases")
        self.save_aliases_button.clicked.connect(self.save_aliases)
        layout.addWidget(self.save_aliases_button, i, 0, 1, 3)

    def save_aliases(self):
        if "aliases" not in self.config:
            self.config["aliases"] = {}
        if "hidden_sensors" not in self.config:
            self.config["hidden_sensors"] = []
        if "hidden_fans" not in self.config:
            self.config["hidden_fans"] = []

        for path, widgets in self.alias_widgets.items():
            self.config["aliases"][path] = widgets["alias_input"].text()
            if widgets["type"] == "sensor":
                if not widgets["visible_checkbox"].isChecked():
                    if path not in self.config["hidden_sensors"]:
                        self.config["hidden_sensors"].append(path)
                else:
                    if path in self.config["hidden_sensors"]:
                        self.config["hidden_sensors"].remove(path)
            elif widgets["type"] == "fan":
                if not widgets["visible_checkbox"].isChecked():
                    if path not in self.config["hidden_fans"]:
                        self.config["hidden_fans"].append(path)
                else:
                    if path in self.config["hidden_fans"]:
                        self.config["hidden_fans"].remove(path)
        
        with open(CONFIG_PATH, "w") as f:
            json.dump(self.config, f, indent=2)
        
        self.update_ui_with_aliases()


    def new_curve(self):
        curve_name = self.curve_name_input.text().strip()
        if not curve_name:
            i = 1
            while f"New Curve {i}" in self.config.get("curves", {}):
                i += 1
            curve_name = f"New Curve {i}"
        
        if curve_name in self.config.get("curves", {}):
            print(f"Curve '{curve_name}' already exists. Please choose a different name.")
            return

        item = QListWidgetItem(curve_name)
        self.curve_list.addItem(item)
        self.curve_list.setCurrentItem(item)
        self.curve_plot.set_points([[20, 0], [80, 100]])
        self.curve_name_input.setText(curve_name)

        if "curves" not in self.config:
            self.config["curves"] = {}
        self.config["curves"][curve_name] = {
            "sensor": self.sensor_combo.currentData(Qt.ItemDataRole.UserRole), 
            "points": [[20, 0], [80, 100]]
        }
        self.save_config()
        self.update_fan_curve_combos()

    def delete_curve(self):
        current_item = self.curve_list.currentItem()
        if current_item:
            curve_name = current_item.text()
            if curve_name in self.config["curves"]: 
                del self.config["curves"][curve_name]
                self.curve_list.takeItem(self.curve_list.row(current_item))
                self.save_config()
                self.update_fan_curve_combos()
            else:
                print(f"Curve '{curve_name}' not found in config.")

    def display_curve(self, item):
        if not item:
            self.curve_name_input.clear()
            self.curve_plot.set_points([])
            self.sensor_combo.setCurrentIndex(0)
            return
        curve_name = item.text()
        self.curve_name_input.setText(curve_name)
        if curve_name in self.config.get("curves", {}):
            curve_data = self.config["curves"][curve_name]
            self.curve_plot.set_points(curve_data["points"])
            sensor_path = curve_data["sensor"]
            # Find the index of the sensor_path in the model
            for i in range(self.sensor_combo_model.rowCount()):
                if self.sensor_combo_model.item(i).data(Qt.ItemDataRole.UserRole) == sensor_path:
                    self.sensor_combo.setCurrentIndex(i)
                    break

    def save_curve(self):
        curve_name = self.curve_name_input.text().strip()
        if not curve_name:
            print("Curve name cannot be empty.")
            return

        current_item = self.curve_list.currentItem()
        old_curve_name = current_item.text() if current_item else None

        if old_curve_name and old_curve_name != curve_name and curve_name in self.config.get("curves", {}):
            print(f"Curve '{curve_name}' already exists. Please choose a different name.")
            return
        
        if old_curve_name and old_curve_name != curve_name:
            self.config["curves"][curve_name] = self.config["curves"].pop(old_curve_name)
            current_item.setText(curve_name)

        sensor_path = self.sensor_combo.currentData(Qt.ItemDataRole.UserRole)
        points = self.curve_plot.points

        if "curves" not in self.config:
            self.config["curves"] = {}
        self.config["curves"][curve_name] = {
            "sensor": sensor_path,
            "points": points
        }
        self.save_config()
        self.update_fan_curve_combos()

    def load_config(self):
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r") as f:
                self.config = json.load(f)
        else:
            self.config = {"curves": {}, "fans": {}, "aliases": {}, "hidden_fans": []}
        
        if "aliases" not in self.config:
            self.config["aliases"] = {}
        if "hidden_sensors" not in self.config:
            self.config["hidden_sensors"] = []
        if "hidden_fans" not in self.config:
            self.config["hidden_fans"] = []
    def update_fan_curve_combos(self):
        curve_names = list(self.config.get("curves", {}).keys())
        for fan_path, widgets in self.fan_widgets.items():
            combo = widgets["combo"]
            current_selection = combo.currentText()
            combo.clear()
            combo.addItems(curve_names)
            if fan_path in self.config.get("fans", {}):
                curve_name = self.config["fans"][fan_path]
                combo.setCurrentText(curve_name)
            elif current_selection in curve_names:
                combo.setCurrentText(current_selection)

    def save_config(self):
        if "fans" not in self.config:
            self.config["fans"] = {}
        for fan_path, widgets in self.fan_widgets.items():
            self.config["fans"][fan_path] = widgets["combo"].currentText()

        if "hardware" not in self.config:
            self.config["hardware"] = {}
            
        for fan_path, widgets in self.fan_widgets.items():
            if "min_speed_spinbox" in widgets:
                self.config["hardware"]["nvidia_min_fan_speed"] = widgets["min_speed_spinbox"].value()

        with open(CONFIG_PATH, "w") as f:
            json.dump(self.config, f, indent=2)
        print(f"Saved settings to {CONFIG_PATH}")
        self.restart_controller()

    def restart_controller(self):
        if self.controller_process:
            self.controller_process.terminate()
            self.controller_process.wait()
        
        if STATUS_PATH.exists():
            STATUS_PATH.unlink()

        self.controller_process = subprocess.Popen(
            [sys.executable, str(Path(__file__).parent / "fan-controller.py")]
        )
        print("Fan controller process restarted.")

    def update_status(self):
        if not STATUS_PATH.exists():
            self.status_bar.showMessage("Controller: STOPPED")
            return

        try:
            with open(STATUS_PATH, "r") as f:
                status_data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            self.status_bar.showMessage("Controller: STATUS UNKNOWN")
            return

        pid = status_data.get("pid")
        try:
            if pid:
                os.kill(pid, 0)
        except OSError:
            self.status_bar.showMessage("Controller: STOPPED")
            if STATUS_PATH.exists():
                STATUS_PATH.unlink()
            return

        controller_status = status_data.get("status", "UNKNOWN")
        if controller_status == "running":
            self.status_bar.showMessage("Controller: RUNNING")
            self.update_sensor_combo(status_data)
        elif controller_status == "error":
            error_message = status_data.get('error_message', 'Unknown error')
            self.status_bar.showMessage(f"Controller: ERROR ({error_message})")
        else:
            self.status_bar.showMessage(f"Controller: {controller_status.upper()}")

        # Update hardware tab
        for fan_path, widgets in self.fan_widgets.items():
            curve_name = self.config.get("fans", {}).get(fan_path)
            if not curve_name:
                continue
            
            curve = self.config.get("curves", {}).get(curve_name)
            if not curve:
                continue

            sensor_path = curve["sensor"]
            temp = status_data.get("sensors", {}).get(sensor_path)
            speed = status_data.get("fans", {}).get(fan_path)

            if temp is not None:
                widgets["temp_label"].setText(f"Temp: {temp:.1f}°C")
            if speed is not None:
                widgets["speed_label"].setText(f"Speed: {speed:.1f}%")

    def closeEvent(self, event):
        self.save_config()
        if self.controller_process:
            self.controller_process.terminate()
        if STATUS_PATH.exists():
            STATUS_PATH.unlink()
        event.accept()


def check_permissions():
    import os
    for path in Path(HWMON_PATH).glob("hwmon*/pwm*"):
        if path.name.endswith("_enable"):
            continue
        if not os.access(path, os.W_OK):
            print(f"No write permission for {path}.")
            print("Please run 'sudo ./setup_permissions.sh' to set the required permissions.")
            return False
    return True

if __name__ == "__main__":
    if not check_permissions():
        sys.exit(1)

    app = QApplication(sys.argv)
    window = FanControlApp()
    window.show()
    sys.exit(app.exec())