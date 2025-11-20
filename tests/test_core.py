"""Tests for the core.py module."""
import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
import json

from fan_controller.core import FanController


class TestFanController(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        self.config_path = Path(self.test_dir) / "config.json"
        self.status_path = Path(self.test_dir) / "status.json"
        
        # Create a basic config
        self.config = {
            "curves": {
                "test_curve": {
                    "sensor": "test_sensor",
                    "points": [[20, 0], [40, 50], [60, 100]]
                }
            },
            "fans": {
                "test_fan": "test_curve"
            }
        }
        
        with open(self.config_path, "w") as f:
            json.dump(self.config, f)

    def test_load_config(self):
        """Test configuration loading."""
        controller = FanController(self.config_path, self.status_path)
        self.assertTrue(controller.load_config())
        self.assertEqual(controller.config["curves"]["test_curve"]["sensor"], "test_sensor")

    def test_calculate_fan_speed(self):
        """Test fan speed calculation from curve."""
        controller = FanController(self.config_path, self.status_path)
        points = [[20, 0], [40, 50], [60, 100]]
        
        # Test exact points
        self.assertEqual(controller.calculate_fan_speed(20, points), 0)
        self.assertEqual(controller.calculate_fan_speed(40, points), 50)
        self.assertEqual(controller.calculate_fan_speed(60, points), 100)
        
        # Test interpolation
        self.assertAlmostEqual(controller.calculate_fan_speed(30, points), 25, delta=0.1)
        self.assertAlmostEqual(controller.calculate_fan_speed(50, points), 75, delta=0.1)

    def test_smooth_speed(self):
        """Test speed smoothing."""
        controller = FanController(self.config_path, self.status_path)
        fan_path = "test_fan"
        
        # Initial speed
        smooth = controller.smooth_speed(50, fan_path, step=10)
        self.assertEqual(smooth, 50)  # First call, no smoothing
        
        # Gradual increase
        controller.last_speeds[fan_path] = 50
        smooth = controller.smooth_speed(80, fan_path, step=10)
        self.assertEqual(smooth, 60)  # Limited by step
        
        # Gradual decrease
        controller.last_speeds[fan_path] = 80
        smooth = controller.smooth_speed(50, fan_path, step=10)
        self.assertEqual(smooth, 70)  # Limited by step

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.test_dir)


if __name__ == "__main__":
    unittest.main()
