
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
            # Enable manual fan control. Some systems require this before every write.
            enable_path = Path(fan_path.replace("pwm", "pwm_enable"))
            if enable_path.exists():
                try:
                    # Only write if it's not already in manual mode to avoid unnecessary writes.
                    if enable_path.read_text().strip() != "1":
                        enable_path.write_text("1")
                        logging.info(f"Set manual fan control for {fan_path}")
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
            # Retry writing to the pwm file to handle cases where the file is temporarily busy
            for i in range(3):
                try:
                    Path(fan_path).write_text(str(speed_pwm))
                    break
                except IOError as e:
                    if e.errno == 16 and i < 2: # errno 16 is "Device or resource busy"
                        time.sleep(0.1)
                        continue
                    raise
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
        
        last_loop_time = time.time()
        last_status_write_time = 0
        last_force_refresh_time = 0
        FORCE_REFRESH_INTERVAL = 60
        STATUS_WRITE_INTERVAL = 2

        while True:
            current_time = time.time()
            
            # Sleep Detection
            if current_time - last_loop_time > 5:
                logging.warning("Sleep detected! (Time jump > 5s). Forcing refresh of all fans.")
                last_speeds.clear() # Clear cache to force re-apply
                # Force re-enable manual mode check
                for fan_path in fans:
                    if "pwm" in fan_path and "_" not in fan_path:
                         enable_path = Path(fan_path.replace("pwm", "pwm_enable"))
                         if enable_path.exists():
                             try:
                                 enable_path.write_text("1")
                                 logging.info(f"Re-enabled manual fan control for {fan_path} after sleep")
                             except IOError as e:
                                 logging.warning(f"Could not re-enable manual fan control for {fan_path}: {e}")

            # Periodic Force Refresh
            if current_time - last_force_refresh_time > FORCE_REFRESH_INTERVAL:
                logging.info("Periodic force refresh executing...")
                last_speeds.clear()
                last_force_refresh_time = current_time

            last_loop_time = current_time

            # Update all sensor temperatures in status
            for sensor_path in all_sensors.values():
                temp = read_temp(sensor_path)
                status["sensors"][sensor_path] = temp

            for fan_path, fan_name in list(fans.items()):
                curve_name = config.get("fans", {}).get(fan_path)

                if not curve_name:
                    continue
                
                if "pwm" in fan_path and "_" in fan_path:
                    continue
                
                if curve_name not in curves:
                    continue

                curve = curves[curve_name]
                sensor_path = curve["sensor"]
                points = curve["points"]

                temp = status["sensors"].get(sensor_path)
                if temp is None:
                    continue

                speed = get_fan_speed_from_curve(temp, points)

                # Smoothing
                last_speed_val = last_speeds.get(fan_path, speed)
                step = 10
                if speed > last_speed_val + step:
                    speed = last_speed_val + step
                elif speed < last_speed_val - step:
                    speed = last_speed_val - step
                
                # Check if we actually need to change speed (Optimization)
                # For nvidia settings, we want to be very careful to avoid spamming
                should_update = False
                if fan_path not in last_speeds:
                    should_update = True
                else:
                    # Only update if changed by more than 1% to avoid jitter
                    if abs(speed - last_speeds[fan_path]) > 1.0:
                         should_update = True
                
                if should_update:
                    set_fan_speed(fan_path, speed, config, last_speeds)
                    logging.info(f"Fan {fan_path}: Temp {temp:.1f}°C -> Speed {speed:.1f}%")
                    last_speeds[fan_path] = speed
                
                # Update fan speeds in status (always update status even if not applied to hardware, for UI)
                status["fans"][fan_path] = speed
            
            # Optimize status writing
            if current_time - last_status_write_time > STATUS_WRITE_INTERVAL:
                with open(STATUS_PATH, "w") as f:
                    json.dump(status, f, indent=2)
                last_status_write_time = current_time

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
