import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import numpy as np
import atexit
import os

from .hardware import Sensor, Fan, find_sensors, find_fans

logger = logging.getLogger(__name__)

class FanController:
    def __init__(self, config_path: Path, status_path: Path):
        self.config_path = config_path
        self.status_path = status_path
        self.config: Dict = {}
        self.sensors: Dict[str, Sensor] = {}
        self.fans: Dict[str, Fan] = {}
        self.last_speeds: Dict[str, float] = {}
        self.status = {
            "pid": os.getpid(),
            "status": "starting",
            "sensors": {},
            "fans": {},
        }
        atexit.register(self._cleanup_status)

    def _cleanup_status(self):
        if self.status_path.exists():
            self.status_path.unlink()

    def load_config(self) -> bool:
        if not self.config_path.exists():
            logger.error(f"Config file not found at {self.config_path}")
            self.status["status"] = "error"
            self.status["error_message"] = "config.json not found"
            self._write_status()
            return False
        
        with open(self.config_path, "r") as f:
            self.config = json.load(f)
        return True

    def _write_status(self):
        with open(self.status_path, "w") as f:
            json.dump(self.status, f, indent=2)

    def discover_hardware(self):
        self.sensors = find_sensors()
        self.fans = find_fans()
        logger.info(f"Found {len(self.sensors)} sensors and {len(self.fans)} fans")

    def calculate_fan_speed(self, temp: float, points: List[Tuple[float, float]]) -> float:
        points = sorted(points)
        temps = [p[0] for p in points]
        speeds = [p[1] for p in points]
        return float(np.interp(temp, temps, speeds))

    def smooth_speed(self, target_speed: float, fan_path: str, step: float = 10.0) -> float:
        last_speed = self.last_speeds.get(fan_path, target_speed)
        if target_speed > last_speed + step:
            return last_speed + step
        elif target_speed < last_speed - step:
            return last_speed - step
        return target_speed

    def run(self):
        if not self.load_config():
            return

        self.discover_hardware()
        
        # Apply min speed for NVIDIA fan if configured
        nvidia_min_speed = self.config.get("hardware", {}).get("nvidia_min_fan_speed", 26)
        if "nvidia-settings" in self.fans:
            from .hardware import NvidiaFan
            if isinstance(self.fans["nvidia-settings"], NvidiaFan):
                self.fans["nvidia-settings"].min_speed = nvidia_min_speed

        self.status["status"] = "running"
        self._write_status()

        try:
            while True:
                # Read all sensor temperatures
                for sensor_path, sensor in self.sensors.items():
                    temp = sensor.read_temp()
                    self.status["sensors"][sensor_path] = temp

                # Apply fan curves
                curves = self.config.get("curves", {})
                fan_assignments = self.config.get("fans", {})

                for fan_path, fan in self.fans.items():
                    curve_name = fan_assignments.get(fan_path)
                    
                    if not curve_name:
                        continue
                    
                    if curve_name not in curves:
                        logger.warning(f"Curve '{curve_name}' not found for fan '{fan_path}'")
                        continue

                    curve = curves[curve_name]
                    sensor_path = curve["sensor"]
                    points = curve["points"]

                    temp = self.status["sensors"].get(sensor_path)
                    if temp is None:
                        continue

                    target_speed = self.calculate_fan_speed(temp, points)
                    smooth_speed = self.smooth_speed(target_speed, fan_path)
                    self.last_speeds[fan_path] = smooth_speed

                    fan.set_speed(smooth_speed)
                    self.status["fans"][fan_path] = smooth_speed
                    logger.info(f"Fan {fan_path}: Temp {temp:.1f}°C -> Speed {smooth_speed:.1f}%")

                self._write_status()
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("Fan controller stopped by user")
        except Exception as e:
            logger.error(f"Unhandled exception: {e}", exc_info=True)
            self.status["status"] = "error"
            self.status["error_message"] = str(e)
            self._write_status()
        finally:
            logger.info("Stopping fan controller.")
            self._cleanup_status()
