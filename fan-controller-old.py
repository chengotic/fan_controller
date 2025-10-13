import time

while True:

    with open("/sys/class/hwmon/hwmon0/temp2_input") as f:
        
        temp = int(f.read()) / 1000

    # if temp < 40:
    #     pwm = 0
    # elif temp < 50:
    #     pwm = 30
    # elif temp < 60:
    #     pwm = 50
    # elif temp < 70:
    #     pwm = 75
    # elif temp < 80:
    #     pwm = 100
    # else:
    #     pwm = 255

    def curve(temp):
        t_min, t_max = 20, 80
        pwm_min, pwm_max = 0, 255

        if temp < t_min:
            return pwm_min
        elif temp < t_max:
            return pwm_max
        else:
            return int(pwm_min + (pwm_max - pwm_min) * (temp - t_min) / (t_max - t_min))

    pwm = curve(temp)

    with open("/sys/class/hwmon/hwmon0/pwm2", "w") as f:
        f.write(str(pwm))

    with open("/sys/class/hwmon/hwmon0/pwm1", "w") as f:
        f.write(str(pwm))

    print(pwm)

    time.sleep(3)