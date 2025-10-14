import time
import subprocess
import json
from pathlib import Path


cpu_step = 20
gpu_step = 10

CONFIG_PATH = Path(__file__).parent / "config.json"
CPU_TEMP_PATH = Path("/sys/class/hwmon/hwmon0/temp2_input")
PWM1_PATH  = Path("/sys/class/hwmon/hwmon0/pwm1")
PWM2_PATH  = Path("/sys/class/hwmon/hwmon0/pwm2")

#load config

if CONFIG_PATH.exists():
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)
    cpu_min_temp = config.get("cpu_min", 40)
    cpu_max_temp = config.get("cpu_max", 80)
    gpu_min_temp = config.get("gpu_min", 40)
    gpu_max_temp = config.get("gpu_max", 80)
else:
    cpu_min_temp = 60
    cpu_max_temp = 80
    gpu_min_temp = 60
    gpu_max_temp = 80

#cpu
def read_cpu_temp():
    raw = int(CPU_TEMP_PATH.read_text().strip())
    return raw / 1000.0

def cpu_curve(temp):
    if temp <= cpu_min_temp:
         return 0
    elif temp >= cpu_max_temp:
         return 255
    return int((temp - cpu_min_temp) * 255 / (cpu_max_temp - cpu_min_temp))

#gpu
def get_gpu_temp():
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
        capture_output=True, text=True
    )
    return int(result.stdout.strip())

def gpu_curve(temp):
    if temp <= gpu_min_temp:
         return 26
    elif temp >= gpu_max_temp:
         return 100
    return int(26 + (temp - gpu_min_temp) * (100 - 26) / (gpu_max_temp - gpu_min_temp))

def set_gpu_fan(speed_percent):
    # clamp between 0–100
    speed_percent = max(0, min(100, int(speed_percent)))
    subprocess.run([
        "nvidia-settings",
        "-a", "[gpu:0]/GPUFanControlState=1",
        "-a", f"[fan:0]/GPUTargetFanSpeed={speed_percent}"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

last_cpu_pwm = None
last_gpu_percent = None

try:
    while True:
        # reload config
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r") as f:
                    config = json.load(f)
                cpu_min_temp = config.get("cpu_min", 40)
                cpu_max_temp = config.get("cpu_max", 80)
                gpu_min_temp = config.get("gpu_min", 40)
                gpu_max_temp = config.get("gpu_max", 80)
            except Exception as e:
                print("Failed to load config:", e)

        # CPU
        cpu_temp = read_cpu_temp()
        cpu_pwm = cpu_curve(cpu_temp)
        if last_cpu_pwm is None:
            last_cpu_pwm =cpu_pwm

        if cpu_pwm > last_cpu_pwm + cpu_step:
            cpu_pwm = last_cpu_pwm + cpu_step
        elif cpu_pwm < last_cpu_pwm - cpu_step:
            cpu_pwm = last_cpu_pwm - cpu_step

        PWM1_PATH.write_text(str(cpu_pwm))
        PWM2_PATH.write_text(str(cpu_pwm))
        last_cpu_pwm = cpu_pwm

        # GPU
        gpu_temp = get_gpu_temp()
        gpu_percent = gpu_curve(gpu_temp)
        if last_gpu_percent is None:
            last_gpu_percent =gpu_percent

        if gpu_percent > last_gpu_percent + gpu_step:
            gpu_percent = last_gpu_percent + gpu_step
        elif gpu_percent < last_gpu_percent - gpu_step:
            gpu_percent = last_gpu_percent - gpu_step

        set_gpu_fan(gpu_percent)
        last_gpu_percent = gpu_percent

        print(f"CPU: {cpu_temp:.1f}°C -> {cpu_pwm}, GPU: {gpu_temp}°C -> {gpu_percent}")
        time.sleep(1)
except KeyboardInterrupt:
    print("Stopped")