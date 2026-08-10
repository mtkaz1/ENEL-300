## Overview

This project is a **Bluetooth-controlled remote robot** built by a 4-member team to compete in an obstacle course and metal/object detection challenge, where we placed **Top 10**. The robot combines custom PCB design, embedded firmware, and real-time sensor integration to navigate obstacles and detect objects autonomously and via manual override.

## Key Features

- **Bluetooth Control**: Real-time remote driving via a Bluetooth serial link, allowing manual navigation through the obstacle course alongside autonomous detection routines.
- **ESP32 Firmware (C)**: Core embedded logic written in **C**, handling motor control via **PWM**, sensor polling, and Bluetooth command parsing simultaneously.
- **Remote Control App (Python)**: Built a **Python** application to send driving commands over Bluetooth, giving the operator real-time manual control during competition runs.
- **Custom PCB Design**: Designed and fabricated a custom PCB to consolidate power distribution, motor drivers, and sensor connections, reducing wiring complexity and improving reliability during competition runs.
- **Object/Metal Detection**: Integrated sensors for object and metal detection, feeding data back to the ESP32 for navigation decisions.
- **PWM Motor Control**: Used **PWM** signals to precisely control motor speed and direction, enabling fine-tuned maneuvering through tight obstacle course sections.

## Development Process

Our team of 4 applied a sprint-based workflow, using Gantt charts and weekly check-ins to track progress and keep hardware and firmware development in sync. This let us parallelize PCB fabrication, firmware development, and mechanical assembly, then integrate and test the full system ahead of competition.

## Results

The robot placed **Top 10** in the obstacle course and object detection competition, validating both the reliability of our custom PCB/hardware stack and the responsiveness of our Bluetooth control and detection firmware under competition conditions.
