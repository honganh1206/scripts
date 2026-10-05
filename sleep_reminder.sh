#!/bin/bash

# sleep_reminder.sh
# Script to remind you to go to sleep at 11:59 PM

# Set the notification title and message
TITLE="Sleep Reminder"
MESSAGE="It's time to go to sleep. Do you have anything interesting enough to stay up for?"
ICON="appointment-soon"  # System icon for reminder

# Function to show notification
show_notification() {
    # Use notify-send without actions
    notify-send -u critical -i "$ICON" "$TITLE" "$MESSAGE"
    
    # If zenity is available, use it for interactive response
    if command -v zenity &> /dev/null; then
        zenity --question --title="$TITLE" --text="$MESSAGE\n\nSnooze for 15 minutes?" --ok-label="Snooze" --cancel-label="Going to sleep"
        if [ $? -eq 0 ]; then
            # User clicked "Snooze"
            sleep 900  # Wait 15 minutes (900 seconds)
            notify-send -u critical -i "$ICON" "$TITLE" "15 minutes have passed. Time to sleep now!"
        fi
    fi
}

# Check if needed commands exist
if ! command -v notify-send &> /dev/null; then
    echo "notify-send is not installed. Installing..."
    sudo apt-get update && sudo apt-get install -y libnotify-bin
fi

# Check if zenity is installed (for interactive notifications)
if ! command -v zenity &> /dev/null; then
    echo "zenity is not installed. Installing..."
    sudo apt-get update && sudo apt-get install -y zenity
fi

# Show the notification
show_notification

# Set up to run every day at 11:59 PM
# You can add this to your crontab by running:
# crontab -e
# Then add the line:
# 59 23 * * * /path/to/sleep_reminder.sh
