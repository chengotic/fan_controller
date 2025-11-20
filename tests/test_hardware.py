"""Tests for the hardware.py module."""
import unittest
from unittest.mock import Mock, patch, MagicMock, mock_open
from pathlib import Path

from fan_controller.hardware import (
    HwmonSensor, NvidiaSensor, HwmonFan, NvidiaFan,
    find_sensors, find_fans
)


class TestHwmonSensor(unittest.TestCase):
    @patch("fan_controller.hardware.Path")
    def test_read_temp(self, mock_path):
        """Test reading temperature from hwmon sensor."""
        mock_path_instance = MagicMock()
        mock_path_instance.read_text.return_value = "45000\n"
        mock_path.return_value = mock_path_instance
        
        sensor = HwmonSensor("/sys/class/hwmon/hwmon0/temp1_input", "CPU")
        temp = sensor.read_temp()
        self.assertEqual(temp, 45.0)


class TestNvidiaSensor(unittest.TestCase):
    @patch("fan_controller.hardware.subprocess.run")
    def test_read_temp(self, mock_run):
        """Test reading temperature from NVIDIA GPU."""
        mock_run.return_value = MagicMock(stdout="65\n")
        
        sensor = NvidiaSensor()
        temp = sensor.read_temp()
        self.assertEqual(temp, 65.0)


class TestHwmonFan(unittest.TestCase):
    @patch("fan_controller.hardware.Path")
    def test_set_speed(self, mock_path):
        """Test setting fan speed."""
        mock_path_instance = MagicMock()
        mock_path.return_value = mock_path_instance
        
        fan = HwmonFan("/sys/class/hwmon/hwmon0/pwm1", "CPU Fan")
        fan.set_speed(50.0)
        
        # Verify write was called (50% of 255 = 127)
        mock_path_instance.write_text.assert_called()


class TestNvidiaFan(unittest.TestCase):
    @patch("fan_controller.hardware.subprocess.run")
    def test_set_speed(self, mock_run):
        """Test setting NVIDIA fan speed."""
        mock_run.return_value = MagicMock(stdout="0\n")  # Not root
        
        fan = NvidiaFan(min_speed=30)
        fan.set_speed(50.0)
        
        # Verify nvidia-settings was called
        mock_run.assert_called()
        args = mock_run.call_args[0][0]
        self.assertIn("nvidia-settings", args)
        self.assertIn("[fan:0]/GPUTargetFanSpeed=50", args)

    @patch("fan_controller.hardware.subprocess.run")
    def test_min_speed_enforcement(self, mock_run):
        """Test that minimum speed is enforced."""
        mock_run.return_value = MagicMock(stdout="0\n")
        
        fan = NvidiaFan(min_speed=30)
        fan.set_speed(20.0)  # Below minimum
        
        args = mock_run.call_args[0][0]
        # Speed should be clamped to min_speed
        self.assertIn("[fan:0]/GPUTargetFanSpeed=30", args)


if __name__ == "__main__":
    unittest.main()
