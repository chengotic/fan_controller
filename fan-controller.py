
import time
import subprocess
import json
from pathlib import Path
import numpy as np
import logging
import os
import atexit

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CONFIG_PATH = Path(__file__).parent / "config.json"
STATUS_PATH = Path(__file__).parent / ".fan_controller_status.json"

HWMON_PATH = "/sys/class/hwmon"

status = {
    "pid": os.getpid(),
    "status": "starting",
    "sensors": {},
    "fans": {},
}

def _cleanup_status():
    if STATUS_PATH.exists():
        STATUS_PATH.unlink()
atexit.register(_cleanup_status)

def get_alias(config, path):
    return config.get("aliases", {}).get(path, path)

def find_sensors():
    sensors = {}
    # Find hwmon sensors
    for path in Path(HWMON_PATH).glob("hwmon*/temp*_input"):
        sensors[str(path)] = str(path)

    # Add GPU sensor
    gpu_sensor_path = "nvidia-smi"
    sensors[gpu_sensor_path] = gpu_sensor_path
    return sensors

def read_temp(sensor_path):
    try:
        if sensor_path == "nvidia-smi":
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, check=True
            )
            return int(result.stdout.strip())
        else:
            raw = int(Path(sensor_path).read_text().strip())
            return raw / 1000.0
    except (FileNotFoundError, ValueError, subprocess.CalledProcessError) as e:
        logging.error(f"Failed to read temperature from {sensor_path}: {e}")
        return None

def set_fan_speed(fan_path, speed, config, last_speeds):
    try:
        if fan_path == "nvidia-settings":
            min_speed = config.get("hardware", {}).get("nvidia_min_fan_speed", 26)
            speed_percent = max(min_speed, min(100, int(speed))) # Clamp between min_speed and 100
            command = [
                "sudo",
                "nvidia-settings",
                "-a", "[gpu:0]/GPUFanControlState=1",
                "-a", f"[fan:0]/GPUTargetFanSpeed={speed_percent}"
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
        else:
            # Enable manual fan control if not already enabled
            if fan_path not in last_speeds:
                enable_path = Path(fan_path.replace("pwm", "pwm_enable"))
                if enable_path.exists():
                    try:
                        enable_path.write_text("1")
                        logging.info(f"Enabled manual fan control for {fan_path}")
                    except IOError as e:
                        logging.warning(f"Could not enable manual fan control for {fan_path}: {e}")

            pwm_max = 255
            pwm_max_path = Path(fan_path.replace("pwm", "pwm_max"))
            if pwm_max_path.exists():
                try:
                    pwm_max = int(pwm_max_path.read_text().strip())
                except (ValueError, FileNotFoundError):
                    logging.warning(f"Could not read {pwm_max_path}, defaulting pwm_max to 255.")

            speed_pwm = max(0, min(pwm_max, int(speed / 100 * pwm_max)))
            Path(fan_path).write_text(str(speed_pwm))
    except (FileNotFoundError, IOError, subprocess.CalledProcessError) as e:
        logging.error(f"Failed to set fan speed for {fan_path}: {e}")

def get_fan_speed_from_curve(temp, points):
    points = sorted(points)
    temps = [p[0] for p in points]
    speeds = [p[1] for p in points]
    return np.interp(temp, temps, speeds)

def main():
    try:
        if not CONFIG_PATH.exists():
            logging.error(f"Config file not found at {CONFIG_PATH}")
            status["status"] = "error"
            status["error_message"] = "config.json not found"
            with open(STATUS_PATH, "w") as f:
                json.dump(status, f)
            return

        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)

        status["status"] = "running"
        with open(STATUS_PATH, "w") as f:
            json.dump(status, f)

        all_sensors = find_sensors()
        curves = config.get("curves", {})
        fans = config.get("fans", {})
        last_speeds = {}

        while True:
            # Update all sensor temperatures in status
            for sensor_path in all_sensors.values():
                temp = read_temp(sensor_path)
                status["sensors"][sensor_path] = temp

            for fan_path, fan_name in list(fans.items()):
                curve_name = config.get("fans", {}).get(fan_path)

                if not curve_name:
                    logging.warning(f"No curve assigned to fan '{fan_path}'. Skipping.")
                    continue
                
                if "pwm" in fan_path and "_" in fan_path:
                    logging.warning(f"Skipping non-fan PWM path: {fan_path}")
                    continue
                
                if curve_name not in curves:
                    logging.warning(f"Curve '{curve_name}' not found for fan '{fan_path}'. Skipping.")
                    continue

                curve = curves[curve_name]
                sensor_path = curve["sensor"]
                points = curve["points"]

                temp = status["sensors"].get(sensor_path)
                if temp is None:
                    continue

                logging.info(f"Using curve points: {points} for temp: {temp}°C")
                speed = get_fan_speed_from_curve(temp, points)
                logging.info(f"Calculated speed (before smoothing): {speed:.1f}%")

                last_speed = last_speeds.get(fan_path, speed)
                step = 10
                if speed > last_speed + step:
                    speed = last_speed + step
                elif speed < last_speed - step:
                    speed = last_speed - step
                last_speeds[fan_path] = speed

                set_fan_speed(fan_path, speed, config, last_speeds)
                logging.info(f"Fan {fan_path}: Temp {temp}°C -> Speed {speed:.1f}%")

                # Update fan speeds in status
                status["fans"][fan_path] = speed

            with open(STATUS_PATH, "w") as f:
                json.dump(status, f, indent=2)

            time.sleep(1)
    except Exception as e:
        logging.error(f"Unhandled exception: {e}", exc_info=True)
        status["status"] = "error"
        status["error_message"] = str(e)
    finally:
        logging.info("Stopping fan controller.")
        if STATUS_PATH.exists():
            with open(STATUS_PATH, "w") as f:
                json.dump(status, f)
        _cleanup_status()

if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()
