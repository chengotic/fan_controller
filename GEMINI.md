# Project Overview

This project is a fan controller for Linux systems. It provides a graphical user interface (GUI) to control the speed of fans based on temperature sensors.

The project consists of two main Python scripts:

- `fan-controller.py`: A script that runs in the background, monitors temperatures, and controls fan speeds based on user-defined curves.
- `gui.py`: A PyQt6-based GUI application that allows users to create and assign fan curves.

The project also includes a `config.json` file for storing the fan control configuration, a `setup_permissions.sh` script for setting the required permissions, and a `notes.txt` file containing some useful commands for monitoring and controlling system hardware.

# Project Structure

```
├── fan-controller.py
├── gui.py
├── config.json
├── setup_permissions.sh
├── notes.txt
└── GEMINI.md
```

- `fan-controller.py`: The core script that reads temperatures and controls fan speeds.
- `gui.py`: The graphical user interface for configuring the fan controller.
- `config.json`: Stores the configuration for the fan controller.
- `setup_permissions.sh`: A script to set the necessary file permissions to run the controller without sudo.
- `notes.txt`: Contains notes and commands for hardware interaction.
- `GEMINI.md`: This file, providing an overview of the project.

# Dependencies

- Python 3
- PyQt6
- pyqtgraph
- numpy
- `nvidia-smi` and `nvidia-settings` (for GPU temperature and fan control)

You can install the Python dependencies using pip:

```bash
pip install PyQt6 pyqtgraph numpy
```

# Building and Running

### 1. Set Permissions

Before running the application for the first time, you need to run the `setup_permissions.sh` script with sudo. This will grant your user account the necessary permissions to control the fans.

```bash
sudo ./setup_permissions.sh
```

### 2. Running the GUI

After setting the permissions, you can run the GUI application without sudo:

```bash
python3 gui.py
```

The GUI allows you to:
- Create, name, and delete fan curves.
- Edit fan curves graphically by clicking on the plot, dragging points, and right-clicking to remove them.
- The graph has fixed temperature (0-100°C) and fan speed (0-100%) ranges and is dynamically sized. Zooming is disabled.
- Assign temperature sensors to curves.
- Assign curves to fans.
- A "Save Hardware Config" button is available on the Hardware tab to explicitly save fan assignments.

The GUI will automatically start the `fan-controller.py` script in the background and restart it whenever the configuration is changed.

### Running the Command-Line Tool

The `fan-controller.py` script is designed to be run in the background by the GUI. It requires `sudo` privileges to control GPU fans via `nvidia-settings`.

```bash
sudo python3 fan-controller.py
```

The script will read the configuration from `config.json` and control the fans accordingly. It includes improved error handling, dynamic PWM range detection, and filters non-fan PWM paths to prevent unnecessary warnings.

# Development Conventions

The project uses Python with the PyQt6 framework for the GUI. It uses `pyqtgraph` for plotting and `numpy` for interpolation. The configuration is stored in a JSON file.