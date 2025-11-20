import sys
import json
from pathlib import Path
import subprocess
import os
from typing import Dict, Optional

from PyQt6.QtCore import Qt, QPointF, QTimer
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGridLayout, QComboBox, QListWidget, QListWidgetItem, QTabWidget, 
    QScrollArea, QLineEdit, QStatusBar, QSpinBox, QCheckBox
)
from PyQt6.QtGui import QStandardItem, QStandardItemModel, QPalette, QColor
import pyqtgraph as pg

from .hardware import find_sensors, find_fans


def get_config_dir() -> Path:
    """Get the configuration directory."""
    # Use current directory if config.json exists (backward compatibility)
    current_dir = Path.cwd()
    if (current_dir / "config.json").exists():
        return current_dir
    
    # Otherwise use ~/.config/fan_controller
    config_dir = Path.home() / ".config" / "fan_controller"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy old config if it exists
    old_config = current_dir / "config.json"
    new_config = config_dir / "config.json"
    if old_config.exists() and not new_config.exists():
        import shutil
        shutil.copy(old_config, new_config)
    
    return config_dir


class FanCurvePlot(pg.PlotWidget):
    """Interactive plot widget for editing fan curves."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Set up plot appearance
        self.setBackground('#2b2b2b')
        self.setLimits(xMin=0, xMax=100, yMin=0, yMax=100)
        self.getPlotItem().vb.setXRange(0, 100, padding=0)
        self.getPlotItem().vb.setYRange(0, 100, padding=0)
        self.setLabel('bottom', 'Temperature', '°C')
        self.setLabel('left', 'Fan Speed', '%')
        self.showGrid(x=True, y=True, alpha=0.3)
        
        # Create curve
        self.curve = self.plot(
            pen=pg.mkPen(color='#00d4ff', width=2),
            symbol='o',
            symbolBrush='#ff6b35',
            symbolSize=10
        )
        self.points = []
        self.dragged_point = None
        self.getPlotItem().vb.setMouseEnabled(x=False, y=False)

    def set_points(self, points):
        """Set the curve points and update the plot."""
        self.points = sorted([[float(p[0]), float(p[1])] for p in points])
        x_coords = [p[0] for p in self.points]
        y_coords = [p[1] for p in self.points]
        self.curve.setData(x_coords, y_coords)

    def mousePressEvent(self, ev):
        pos = self.getPlotItem().vb.mapSceneToView(QPointF(ev.pos()))
        x, y = pos.x(), pos.y()

        # Find closest point
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
                # Add new point
                if 0 <= x <= 100 and 0 <= y <= 100:
                    self.points.append([x, y])
                    self.set_points(self.points)
                    self.dragged_point = len(self.points) - 1

        elif ev.button() == Qt.MouseButton.RightButton:
            # Remove point
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
    """Main application window for fan controller GUI."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fan Controller")
        self.resize(900, 700)
        
        # Set up config paths
        self.config_dir = get_config_dir()
        self.config_path = self.config_dir / "config.json"
        self.status_path = self.config_dir / ".fan_controller_status.json"
        
        # Apply dark theme
        self.apply_dark_theme()
        
        # Create tabs
        self.tabs = QTabWidget()
        self.hardware_tab = QWidget()
        self.curves_tab = QWidget()
        self.aliases_tab = QWidget()

        self.tabs.addTab(self.hardware_tab, "Hardware")
        self.tabs.addTab(self.curves_tab, "Curves")
        self.tabs.addTab(self.aliases_tab, "Aliases")

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tabs)
        self.status_bar = QStatusBar()
        main_layout.addWidget(self.status_bar)
        self.setLayout(main_layout)

        # Initialize data
        self.load_config()
        self.controller_process = None
        self.sensors = {}
        self.sensor_items = {}

        # Initialize UI
        self.init_aliases_tab()
        self.init_hardware_tab()
        self.init_curves_tab()
        self.update_ui_with_aliases()

        # Start status update timer
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(1000)

        # Start controller
        self.restart_controller()

    def apply_dark_theme(self):
        """Apply a modern dark theme to the application."""
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(35, 35, 35))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Base, QColor(45, 45, 45))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
        palette.setColor(QPalette.ColorRole.Link, QColor(0, 212, 255))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 212, 255))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
        self.setPalette(palette)

        # Additional styling
        self.setStyleSheet("""
            QWidget {
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 10pt;
            }
            QPushButton {
                background-color: #00d4ff;
                color: #000;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00b8e6;
            }
            QPushButton:pressed {
                background-color: #0099c2;
            }
            QLineEdit, QComboBox, QSpinBox {
                background-color: #3d3d3d;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 5px;
                color: #fff;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border: 1px solid #00d4ff;
            }
            QTabWidget::pane {
                border: 1px solid #555;
                background-color: #2b2b2b;
            }
            QTabBar::tab {
                background-color: #3d3d3d;
                color: #fff;
                padding: 10px;
                border: 1px solid #555;
            }
            QTabBar::tab:selected {
                background-color: #00d4ff;
                color: #000;
            }
            QStatusBar {
                background-color: #1e1e1e;
                color: #fff;
            }
            QListWidget {
                background-color: #3d3d3d;
                border: 1px solid #555;
                border-radius: 3px;
            }
            QListWidget::item:selected {
                background-color: #00d4ff;
                color: #000;
            }
        """)

    def get_alias(self, path: str) -> str:
        """Get the alias for a hardware path."""
        return self.config.get("aliases", {}).get(path, path)

    def load_config(self):
        """Load configuration from file."""
        if self.config_path.exists():
            with open(self.config_path, "r") as f:
                self.config = json.load(f)
        else:
            self.config = {
                "curves": {},
                "fans": {},
                "aliases": {},
                "hidden_fans": [],
                "hidden_sensors": []
            }
        
        # Ensure all required keys exist
        for key in ["aliases", "hidden_sensors", "hidden_fans"]:
            if key not in self.config:
                self.config[key] = [] if "hidden" in key else {}

    def save_config(self):
        """Save configuration to file."""
        if "fans" not in self.config:
            self.config["fans"] = {}
        
        for fan_path, widgets in self.fan_widgets.items():
            self.config["fans"][fan_path] = widgets["combo"].currentText()

        if "hardware" not in self.config:
            self.config["hardware"] = {}
            
        for fan_path, widgets in self.fan_widgets.items():
            if "min_speed_spinbox" in widgets:
                self.config["hardware"]["nvidia_min_fan_speed"] = widgets["min_speed_spinbox"].value()

        with open(self.config_path, "w") as f:
            json.dump(self.config, f, indent=2)
        
        self.restart_controller()

    def restart_controller(self):
        """Restart the fan controller daemon."""
        if self.controller_process:
            self.controller_process.terminate()
            self.controller_process.wait()
        
        if self.status_path.exists():
            self.status_path.unlink()

        # Use the installed package entry point
        self.controller_process = subprocess.Popen(
            [sys.executable, "-m", "fan_controller.main"],
            env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent)}
        )

    def update_status(self):
        """Update the status bar and hardware display."""
        if not self.status_path.exists():
            self.status_bar.showMessage("Controller: STOPPED")
            return

        try:
            with open(self.status_path, "r") as f:
                status_data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            self.status_bar.showMessage("Controller: STATUS UNKNOWN")
            return

        # Check if process is running
        pid = status_data.get("pid")
        try:
            if pid:
                os.kill(pid, 0)
        except OSError:
            self.status_bar.showMessage("Controller: STOPPED")
            if self.status_path.exists():
                self.status_path.unlink()
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

    def update_sensor_combo(self, status_data):
        """Update sensor combo boxes with current temperatures."""
        for sensor_path, item in self.sensor_items.items():
            temp = status_data.get("sensors", {}).get(sensor_path)
            display_text = self.get_alias(sensor_path)
            if temp is not None:
                display_text += f" ({temp:.1f}°C)"
            item.setText(display_text)

    def update_ui_with_aliases(self):
        """Update UI with current aliases."""
        for path, widgets in self.alias_widgets.items():
            widgets["alias_input"].setText(self.get_alias(path))
            if widgets["type"] == "fan":
                widgets["visible_checkbox"].setChecked(
                    path not in self.config.get("hidden_fans", [])
                )
            elif widgets["type"] == "sensor":
                widgets["visible_checkbox"].setChecked(
                    path not in self.config.get("hidden_sensors", [])
                )

        self.sensors = self.find_sensors()
        self.init_hardware_tab()
        self.init_curves_tab()
        self.update_fan_curve_combos()

    def find_sensors(self) -> Dict[str, str]:
        """Find all visible sensors."""
        all_sensors = find_sensors()
        sensors = {}
        for path in all_sensors.keys():
            if path not in self.config.get("hidden_sensors", []):
                name = self.get_alias(path)
                sensors[name] = path
        return sensors

    def find_fans(self) -> Dict[str, str]:
        """Find all visible fans."""
        all_fans = find_fans()
        fans = {}
        for path in all_fans.keys():
            if path not in self.config.get("hidden_fans", []):
                name = self.get_alias(path)
                fans[name] = path
        return fans

    def init_hardware_tab(self):
        """Initialize the hardware tab."""
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
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # Add headers
        layout.addWidget(QLabel("<b>Fan</b>"), 0, 0)
        layout.addWidget(QLabel("<b>Curve</b>"), 0, 1)
        layout.addWidget(QLabel("<b>Temperature</b>"), 0, 2)
        layout.addWidget(QLabel("<b>Speed</b>"), 0, 3)

        self.fan_widgets = {}
        fans = self.find_fans()
        i = 1
        for fan_name, fan_path in fans.items():
            label = QLabel(fan_name)
            combo = QComboBox()
            temp_label = QLabel("--°C")
            speed_label = QLabel("--%")
            
            layout.addWidget(label, i, 0)
            layout.addWidget(combo, i, 1)
            layout.addWidget(temp_label, i, 2)
            layout.addWidget(speed_label, i, 3)
            
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
                min_speed_spinbox.setValue(
                    self.config.get("hardware", {}).get("nvidia_min_fan_speed", 26)
                )
                layout.addWidget(min_speed_label, i, 4)
                layout.addWidget(min_speed_spinbox, i, 5)
                widgets["min_speed_spinbox"] = min_speed_spinbox

            self.fan_widgets[fan_path] = widgets
            i += 1

        layout.setRowStretch(i, 1)
        layout.setColumnStretch(6, 1)

        save_button = QPushButton("Save Hardware Config")
        save_button.clicked.connect(self.save_config)
        layout.addWidget(save_button, i + 1, 0, 1, 2)

    def init_curves_tab(self):
        """Initialize the curves tab."""
        # Clear existing widgets
        if self.curves_tab.layout() is not None:
            while self.curves_tab.layout().count():
                item = self.curves_tab.layout().takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
        else:
            self.curves_tab.setLayout(QHBoxLayout())
        
        layout = self.curves_tab.layout()

        # Curve list on the left
        self.curve_list = QListWidget()
        self.curve_list.currentItemChanged.connect(self.display_curve)
        layout.addWidget(self.curve_list, 1)

        # Curve editor on the right
        scroll = QScrollArea()
        layout.addWidget(scroll, 3)
        content = QWidget()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        curve_editor_layout = QVBoxLayout(content)

        # Plot
        self.curve_plot = FanCurvePlot()
        self.curve_plot.setMinimumHeight(400)
        curve_editor_layout.addWidget(self.curve_plot)

        # Curve name input
        curve_name_layout = QHBoxLayout()
        curve_editor_layout.addLayout(curve_name_layout)
        curve_name_layout.addWidget(QLabel("Curve Name:"))
        self.curve_name_input = QLineEdit()
        curve_name_layout.addWidget(self.curve_name_input)

        # Sensor selection
        sensor_layout = QHBoxLayout()
        curve_editor_layout.addLayout(sensor_layout)
        sensor_layout.addWidget(QLabel("Sensor:"))
        self.sensor_combo = QComboBox()
        self.sensor_combo_model = QStandardItemModel()
        self.sensor_combo.setModel(self.sensor_combo_model)
        sensor_layout.addWidget(self.sensor_combo)

        # Populate sensor combo
        self.sensor_items = {}
        for sensor_name, sensor_path in self.sensors.items():
            item = QStandardItem()
            item.setData(sensor_path, Qt.ItemDataRole.UserRole)
            item.setText(sensor_name)
            self.sensor_items[sensor_path] = item
            self.sensor_combo_model.appendRow(item)

        # Buttons
        button_layout = QHBoxLayout()
        curve_editor_layout.addLayout(button_layout)
        
        new_curve_button = QPushButton("New Curve")
        new_curve_button.clicked.connect(self.new_curve)
        save_curve_button = QPushButton("Save Curve")
        save_curve_button.clicked.connect(self.save_curve)
        delete_curve_button = QPushButton("Delete Curve")
        delete_curve_button.clicked.connect(self.delete_curve)
        
        button_layout.addWidget(new_curve_button)
        button_layout.addWidget(save_curve_button)
        button_layout.addWidget(delete_curve_button)
        
        # Populate curve list
        self.curve_list.clear()
        for curve_name in self.config.get("curves", {}):
            self.curve_list.addItem(curve_name)

    def init_aliases_tab(self):
        """Initialize the aliases tab."""
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
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        self.alias_widgets = {}
        all_fans = find_fans()
        all_sensors = find_sensors()

        # Headers
        layout.addWidget(QLabel("<b>Device Path</b>"), 0, 0)
        layout.addWidget(QLabel("<b>Alias</b>"), 0, 1)
        layout.addWidget(QLabel("<b>Visible</b>"), 0, 2)
        
        i = 1
        for path in all_fans.keys():
            path_label = QLabel(path)
            alias_input = QLineEdit()
            visible_checkbox = QCheckBox()
            visible_checkbox.setChecked(
                path not in self.config.get("hidden_fans", [])
            )

            layout.addWidget(path_label, i, 0)
            layout.addWidget(alias_input, i, 1)
            layout.addWidget(visible_checkbox, i, 2)
            self.alias_widgets[path] = {
                "alias_input": alias_input,
                "visible_checkbox": visible_checkbox,
                "type": "fan"
            }
            i += 1

        for path in all_sensors.keys():
            path_label = QLabel(path)
            alias_input = QLineEdit()
            visible_checkbox = QCheckBox()
            visible_checkbox.setChecked(
                path not in self.config.get("hidden_sensors", [])
            )

            layout.addWidget(path_label, i, 0)
            layout.addWidget(alias_input, i, 1)
            layout.addWidget(visible_checkbox, i, 2)
            self.alias_widgets[path] = {
                "alias_input": alias_input,
                "visible_checkbox": visible_checkbox,
                "type": "sensor"
            }
            i += 1

        save_button = QPushButton("Save Aliases")
        save_button.clicked.connect(self.save_aliases)
        layout.addWidget(save_button, i, 0, 1, 3)

    def save_aliases(self):
        """Save alias configuration."""
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
        
        with open(self.config_path, "w") as f:
            json.dump(self.config, f, indent=2)
        
        self.update_ui_with_aliases()

    def new_curve(self):
        """Create a new fan curve."""
        curve_name = self.curve_name_input.text().strip()
        if not curve_name:
            i = 1
            while f"New Curve {i}" in self.config.get("curves", {}):
                i += 1
            curve_name = f"New Curve {i}"
        
        if curve_name in self.config.get("curves", {}):
            return

        item = QListWidgetItem(curve_name)
        self.curve_list.addItem(item)
        self.curve_list.setCurrentItem(item)
        self.curve_plot.set_points([[20, 0], [80, 100]])
        self.curve_name_input.setText(curve_name)

        if "curves" not in self.config:
            self.config["curves"] = {}
        
        # Get first sensor if available
        sensor_path = self.sensor_combo.currentData(Qt.ItemDataRole.UserRole)
        if not sensor_path and len(self.sensors) > 0:
            sensor_path = list(self.sensors.values())[0]
        
        self.config["curves"][curve_name] = {
            "sensor": sensor_path,
            "points": [[20, 0], [80, 100]]
        }
        self.save_config()
        self.update_fan_curve_combos()

    def delete_curve(self):
        """Delete the selected curve."""
        current_item = self.curve_list.currentItem()
        if current_item:
            curve_name = current_item.text()
            if curve_name in self.config["curves"]:
                del self.config["curves"][curve_name]
                self.curve_list.takeItem(self.curve_list.row(current_item))
                self.save_config()
                self.update_fan_curve_combos()

    def display_curve(self, item):
        """Display the selected curve in the plot."""
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
        """Save the current curve."""
        curve_name = self.curve_name_input.text().strip()
        if not curve_name:
            return

        current_item = self.curve_list.currentItem()
        old_curve_name = current_item.text() if current_item else None

        if old_curve_name and old_curve_name != curve_name:
            if curve_name in self.config.get("curves", {}):
                return
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

    def update_fan_curve_combos(self):
        """Update fan curve combo boxes with available curves."""
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

    def closeEvent(self, event):
        """Handle application close."""
        self.save_config()
        if self.controller_process:
            self.controller_process.terminate()
        if self.status_path.exists():
            self.status_path.unlink()
        event.accept()


def check_permissions() -> bool:
    """Check if we have write permissions for hardware control."""
    import os
    from pathlib import Path
    
    hwmon_path = Path("/sys/class/hwmon")
    if not hwmon_path.exists():
        return True  # No hwmon, assume OK
    
    for path in hwmon_path.glob("hwmon*/pwm*"):
        if path.name.endswith("_enable"):
            continue
        if not os.access(path, os.W_OK):
            print(f"No write permission for {path}.")
            print("Please run 'sudo ./setup_permissions.sh' to set the required permissions.")
            return False
    return True


def main():
    """Main entry point for the GUI."""
    if not check_permissions():
        sys.exit(1)

    app = QApplication(sys.argv)
    window = FanControlApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
