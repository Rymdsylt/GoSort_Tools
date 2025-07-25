# GoSort: Intelligent Waste Segregation System

An automated waste segregation system that combines computer vision, robotics, and data management to intelligently sort waste materials.

## Quick Start

To test the application, simply run:
```bash
run.bat
```
All necessary setup and instructions are handled inside the batch file.

## Developer Guide

### 🔧 Arduino Hardware Setup

#### Component Connections
- **Pan Servo:** Connected to D8
- **Tilt Servo:** Connected to D9
- **LCD Display:** 1602 LCD with I2C module for simplified wiring and control

### 🔁 System Communication

#### Arduino Communication
- Serial connection handles data transfer between Python and Arduino
- Arduino Mega 2560 receives serialized commands from the Python application
- Bi-directional communication enables real-time debugging and system feedback

#### Database Integration
- System integrates with XAMPP Server (MySQL Database)
- Automatic data logging after each successful sorting operation
- Enables:
  - Admin monitoring
  - System analytics
  - Report generation through GoSort admin panel

## Project Structure
```
├── GoSort.ino              # Arduino control code
├── GoSort.py               # Main Python application
├── GoSort_Detect.py        # Object detection module
├── gosort_config.json      # Configuration settings
└── run.bat                 # Main execution script
```
