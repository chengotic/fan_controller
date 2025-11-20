#!/bin/bash

# This script sets the necessary permissions for the fan controller to run without sudo.
# It needs to be run with sudo itself.

# Find all hwmon directories
for hwmon in /sys/class/hwmon/hwmon*; do
  # Enable all pwm controls
  for pwm_enable in "$hwmon"/pwm*_enable; do
    if [ -f "$pwm_enable" ]; then
      echo 1 > "$pwm_enable"
      echo "Enabled $pwm_enable"
    fi
  done

  # Change permissions for pwm files
  for pwm in "$hwmon"/pwm*; do
    if [ -f "$pwm" ]; then
      chown "$SUDO_USER" "$pwm"
      echo "Changed owner of $pwm to $SUDO_USER"
    fi
  done
done

# Set permissions for nvidia-settings if available
if command -v nvidia-settings &> /dev/null; then
    echo "Configuring passwordless sudo for nvidia-settings..."
    SUDOERS_FILE="/etc/sudoers.d/99-fan-controller-nvidia"
    # Remove previous sudoers file if it exists to avoid conflicts
    if [ -f "$SUDOERS_FILE" ]; then
        rm "$SUDOERS_FILE"
        echo "Removed existing $SUDOERS_FILE"
    fi
    echo "Creating $SUDOERS_FILE..."
    # Allow the user to run any nvidia-settings command without a password (for debugging)
    echo "$SUDO_USER ALL=(ALL) NOPASSWD: /usr/bin/nvidia-settings *" | tee "$SUDOERS_FILE"
    echo "Permissions for nvidia-settings configured."
else
    echo "nvidia-settings not found, skipping GPU configuration."
fi

echo "Permissions set. You can now run the GUI without sudo."
