import abc
import logging
import subprocess
from pathlib import Path
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

class Sensor(abc.ABC):
    def __init__(self, path: str, name: str):
        self.path = path
        self.name = name

    @abc.abstractmethod
    def read_temp(self) -> Optional[float]:
        pass

class HwmonSensor(Sensor):
    def read_temp(self) -> Optional[float]:
        try:
            raw = int(Path(self.path).read_text().strip())
            return raw / 1000.0
        except (FileNotFoundError, ValueError, OSError) as e:
            logger.error(f"Failed to read temperature from {self.path}: {e}")
            return None

class NvidiaSensor(Sensor):
    def __init__(self):
        super().__init__("nvidia-smi", "NVIDIA GPU")

    def read_temp(self) -> Optional[float]:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, check=True
            )
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError, FileNotFoundError) as e:
            logger.error(f"Failed to read NVIDIA GPU temperature: {e}")
            return None

class Fan(abc.ABC):
    def __init__(self, path: str, name: str):
        self.path = path
        self.name = name

    @abc.abstractmethod
    def set_speed(self, speed: float):
        pass

class HwmonFan(Fan):
    def __init__(self, path: str, name: str):
        super().__init__(path, name)
        self._enable_manual_control()

    def _enable_manual_control(self):
        enable_path = Path(self.path.replace("pwm", "pwm_enable"))
        if enable_path.exists():
            try:
                # Try writing 1 for manual control (standard for many chips)
                enable_path.write_text("1")
                logger.info(f"Enabled manual fan control for {self.path}")
            except OSError as e:
                logger.warning(f"Could not enable manual fan control for {self.path}: {e}")

    def set_speed(self, speed: float):
        try:
            pwm_max = 255
            pwm_max_path = Path(self.path.replace("pwm", "pwm_max"))
            if pwm_max_path.exists():
                try:
                    pwm_max = int(pwm_max_path.read_text().strip())
                except (ValueError, OSError):
                    pass

            speed_pwm = max(0, min(pwm_max, int(speed / 100 * pwm_max)))
            Path(self.path).write_text(str(speed_pwm))
        except (FileNotFoundError, OSError) as e:
            logger.error(f"Failed to set fan speed for {self.path}: {e}")

class NvidiaFan(Fan):
    def __init__(self, min_speed: int = 26):
        super().__init__("nvidia-settings", "NVIDIA GPU Fan")
        self.min_speed = min_speed

    def set_speed(self, speed: float):
        try:
            speed_percent = max(self.min_speed, min(100, int(speed)))
            command = [
                "nvidia-settings",
                "-a", "[gpu:0]/GPUFanControlState=1",
                "-a", f"[fan:0]/GPUTargetFanSpeed={speed_percent}"
            ]
            # Check if we are running as root, if not, try sudo (though sudo inside python is tricky)
            # Ideally the service runs as root.
            if subprocess.run(["id", "-u"], capture_output=True, text=True).stdout.strip() != "0":
                 command.insert(0, "sudo")

            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
             logger.error(f"Failed to set NVIDIA fan speed: {e}")

def find_sensors() -> Dict[str, Sensor]:
    sensors = {}
    hwmon_path = Path("/sys/class/hwmon")
    if hwmon_path.exists():
        for path in hwmon_path.glob("hwmon*/temp*_input"):
            sensors[str(path)] = HwmonSensor(str(path), str(path))
    
    # Check for NVIDIA
    try:
        subprocess.run(["nvidia-smi"], check=True, capture_output=True)
        sensors["nvidia-smi"] = NvidiaSensor()
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
        
    return sensors

def find_fans() -> Dict[str, Fan]:
    fans = {}
    hwmon_path = Path("/sys/class/hwmon")
    if hwmon_path.exists():
        for path in hwmon_path.glob("hwmon*/pwm[0-9]*"):
            if "_" in path.name: # Skip attributes like pwm1_enable
                continue
            fans[str(path)] = HwmonFan(str(path), str(path))

    # Check for NVIDIA settings
    try:
        subprocess.run(["nvidia-settings", "-v"], check=True, capture_output=True)
        fans["nvidia-settings"] = NvidiaFan()
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    return fans
