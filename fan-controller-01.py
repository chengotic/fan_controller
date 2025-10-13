import time
from pathlib import Path
import subprocess

TEMP_PATH = Path("/sys/class/hwmon/hwmon0/temp2_input")
PWM1_PATH  = Path("/sys/class/hwmon/hwmon0/pwm1")
PWM2_PATH  = Path("/sys/class/hwmon/hwmon0/pwm2")

pwm_diffrence = 5

def get_gpu_temp():
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
        capture_output=True, text=True
    )
    return int(result.stdout.strip())
    

def set_gpu_fan(speed_percent):
    subprocess.run([
        "nvidia-settings",
        "-a", f"[fan:0]/GPUTargetFanSpeed={speed_percent}"
    ])



def read_temp_c():
    raw = int(TEMP_PATH.read_text().strip())
    return raw / 1000.0 

def curve(temp, t_min=40.0, t_max=80.0, pwm_min=60, pwm_max=255):
    if t_min >= t_max:
        t_min, t_max = sorted((t_min, t_max))

    ratio = (temp - t_min) / (t_max - t_min)

    if ratio < 0:
        ratio = 0.0
    elif ratio > 1:
        ratio = 1.0
    return int(pwm_min + ratio * (pwm_max - pwm_min))

last_pwm = None

try:
    while True:
        temp = read_temp_c()
        pwm = curve(temp, t_min=60.0, t_max=80.0, pwm_min=0, pwm_max=255)

        print(f"temp={temp:.1f}°C  => pwm={pwm} (last={last_pwm})")

        if last_pwm is None or abs(pwm - last_pwm) >= pwm_diffrence:
            PWM1_PATH.write_text(str(pwm))
            PWM2_PATH.write_text(str(pwm))
            last_pwm = pwm
        time.sleep(2)
except KeyboardInterrupt:
    print("Stopped")
