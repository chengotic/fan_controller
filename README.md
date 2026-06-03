# Fan Controller

A Linux fan controller with an intuitive graphical interface.

## Features

**Modern UI**: Beautiful dark-themed GUI built with PyQt6  
**Interactive Curves**: Click-and-drag curve editor for precise control  
**Hardware Support**: Works with standard Linux `hwmon` sensors/fans and NVIDIA GPUs  
**Custom Aliases**: Name your sensors and fans for easy identification  
**Real-time Monitoring**: Live temperature and fan speed display  
**Smooth Control**: Gradual speed changes to prevent sudden fan speed jumps  

## Installation

### From Source

1. **Clone the repository:**
   ```bash
   git clone https://github.com/chengotic/fan_controller.git
   cd fan_controller
   ```

2. **Install the package:**
   
   Using a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Linux/Mac
   pip install -e .
   ```
   
   Or system-wide (requires `--break-system-packages` on some distros):
   ```bash
   pip install -e . --break-system-packages
   ```

   > #### Note on `PATH`
   >
   > If you install the package system-wide, `pip` may install the executables to `~/.local/bin`. If this directory is not in your `PATH`, you will get a "command not found" error.
   >
   > You can add it to your `PATH` for the current session with:
   >
   > ```bash
   > export PATH="$HOME/.local/bin:$PATH"
   > ```
   >
   > To make this change permanent, add this line to your shell's startup file (e.g., `~/.bashrc`, `~/.zshrc`).

3. **Set up permissions:**
   
   Run the setup script to grant the necessary permissions for controlling fans without `sudo`:
   ```bash
   sudo ./setup_permissions.sh
   ```

## Usage

### GUI Application

Launch the graphical interface:

```bash
fan-controller-gui
```

**Tabs:**
- **Hardware**: Assign fan curves to fans, view real-time temperatures and speeds
- **Curves**: Create and edit fan curves with an interactive graph
- **Aliases**: Rename sensors and fans, hide unused hardware

**Curve Editor:**
- **Left-click**: Add or drag points
- **Right-click**: Remove points
- Points are automatically sorted by temperature

### Daemon (CLI)

The daemon runs automatically when you launch the GUI. To run it manually:

```bash
fan-controller  # May require sudo for NVIDIA GPU control
```

## Troubleshooting

### Motherboard sensors or fans not detected

If the application doesn't show your motherboard's temperature sensors or fan controls (e.g., for CPU and case fans), it's likely that the necessary kernel module is not loaded. This can be common after a fresh OS installation.

You can use the `sensors-detect` command, which is part of the `lm-sensors` package, to identify the required module.

1.  **Install `lm-sensors`**: If you don't have it, install it using your distribution's package manager (e.g., `sudo apt install lm-sensors`, `sudo pacman -S lm-sensors`).

2.  **Run `sensors-detect`**:
    ```bash
    sudo sensors-detect
    ```
    It's generally safe to accept the default answers (press ENTER) for all questions.

3.  **Load the module**: At the end of the script, `sensors-detect` will suggest one or more modules to load. For example, for many modern AMD motherboards (like the ASRock B550 series), the suggested module is `nct6775`.

    You can load the module for the current session with:
    ```bash
    sudo modprobe <module_name>  # e.g., sudo modprobe nct6775
    ```

4.  **Make it permanent**: `sensors-detect` will typically offer to create a configuration file in `/etc/modules-load.d/` to load the module automatically on boot. It's recommended to accept this.

5.  **Restart the fan controller**: After loading the new module, restart the `fan-controller-gui` to see the new sensors and fans. You may also need to run the `clean_config.py` script included in this repository to clean up any stale entries from your configuration file.

## Configuration

Configuration is stored in `~/.config/fan_controller/config.json` (or current directory if `config.json` exists for backward compatibility).

Example configuration structure:
```json
{
  "curves": {
    "Silent": {
      "sensor": "/sys/class/hwmon/hwmon0/temp1_input",
      "points": [[20, 0], [60, 50], [80, 100]]
    }
  },
  "fans": {
    "/sys/class/hwmon/hwmon0/pwm1": "Silent"
  },
  "aliases": {
    "/sys/class/hwmon/hwmon0/temp1_input": "CPU Temperature"
  }
}
```

## Development

### Project Structure

```
fan_controller/
├── src/fan_controller/
│   ├── __init__.py       # Package initialization
│   ├── core.py           # Fan controller logic
│   ├── hardware.py       # Hardware abstraction layer
│   ├── gui.py            # PyQt6 GUI application
│   └── main.py           # Entry points
├── tests/                # Unit tests
├── pyproject.toml        # Package configuration
└── README.md             # This file
```

### Running Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

All tests should pass:
- `test_core.py`: Tests for curve calculation and speed smoothing
- `test_hardware.py`: Tests for sensor/fan abstraction

### Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes with tests
4. Ensure all tests pass
5. Submit a pull request

## Requirements

- Python 3.8+
- PyQt6
- pyqtgraph
- numpy
- Linux with `hwmon` support
- (Optional) NVIDIA GPU with `nvidia-smi` and `nvidia-settings`

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

This is a personal project, my first full application developed on my own, and it is not intended to be a professional product.

Built for the Linux community to provide better fan control options.
