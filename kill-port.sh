#!/bin/bash

# Script to find and kill process using a specific port
# Usage: ./kill-port.sh <port_number>

# Check if port number is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <port_number>"
    echo "Example: $0 3000"
    exit 1
fi

PORT=$1

# Check if port is a valid number
if ! [[ "$PORT" =~ ^[0-9]+$ ]]; then
    echo "Error: Port must be a number"
    exit 1
fi

echo "Looking for process using port $PORT..."

# Find the process ID using the port
PID=$(lsof -ti:$PORT)

# Check if any process was found
if [ -z "$PID" ]; then
    echo "No process found using port $PORT"
    exit 0
fi

# Display process information before killing
echo "Found process(es) with PID: $PID"
echo "Process details:"
lsof -i:$PORT

# Ask for confirmation
read -p "Do you want to kill this process? (y/n): " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Kill the process
    kill -9 $PID
    
    # Verify the process was killed
    if [ $? -eq 0 ]; then
        echo "Process $PID killed successfully"
        echo "Port $PORT is now available"
    else
        echo "Failed to kill process $PID"
        exit 1
    fi
else
    echo "Operation cancelled"
    exit 0
fi
