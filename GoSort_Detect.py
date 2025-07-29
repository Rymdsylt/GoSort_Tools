from ultralytics import YOLO
import cv2
import numpy as np
from threading import Thread, Lock
from queue import Queue
import time
import torch
import requests
import json
import os
import socket
import concurrent.futures
import threading
import sys
import msvcrt

def is_maintenance_mode():
    return os.path.exists('python_maintenance_mode.txt')

def load_config():
    config_file = 'gosort_config.json'
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            return json.load(f)
    return {'ip_address': None, 'sorter_id': None}

def save_config(config):
    with open('gosort_config.json', 'w') as f:
        json.dump(config, f)

def scan_network():
    print("\nScanning network for available devices...")
    available_ips = []
    gosort_ips = []
    
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = '127.0.0.1'
    finally:
        s.close()
    ip_parts = local_ip.split('.')
    network_prefix = '.'.join(ip_parts[:3])
    
    network_ips = [f"{network_prefix}.{i}" for i in range(1, 255)]
    total_ips = len(network_ips)
    scanned_ips = 0
    print_lock = threading.Lock()

    def update_progress():
        nonlocal scanned_ips
        with print_lock:
            scanned_ips += 1
            progress = (scanned_ips / total_ips) * 100
            print(f"\rScanning network... {progress:.1f}% complete", end="", flush=True)

    def check_ip(ip):
        try:
            response = requests.get(f"http://{ip}/GoSort_Web/gs_DB/trash_detected.php", 
                                 timeout=0.5)
            if response.status_code == 200 or (
                response.status_code == 400 and 
                "No trash type provided" in response.text
            ):
                gosort_ips.append(str(ip))
            else:
                available_ips.append(str(ip))
        except:
            pass
        update_progress()
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        executor.map(check_ip, network_ips)

    print("\n\nScan complete!")
    
    # Sort and remove duplicates
    gosort_ips = sorted(list(set(gosort_ips)))
    available_ips = sorted(list(set(available_ips) - set(gosort_ips)))
    
    return gosort_ips, available_ips

def check_server(ip):
    print("\rChecking server...", end="", flush=True)
    try:
        response = requests.get(f"http://{ip}/GoSort_Web/gs_DB/trash_detected.php", timeout=5)
        # The server returns 400 with "No trash type provided" if it exists
        if response.status_code == 200 or (response.status_code == 400 and "No trash type provided" in response.text):
            print("\r✅ Server connection successful!")
            return True
        print("\r❌ GoSort does not exist in this server")
        return False
    except requests.exceptions.RequestException:
        print("\r❌ GoSort does not exist in this server")
        return False

def get_ip_address():
    config = load_config()
    ip = config.get('ip_address')
    
    while True:
        if not ip:
            # Scan network for available IPs
            gosort_ips, available_ips = scan_network()
            
            if not gosort_ips and not available_ips:
                print("\nNo devices found in the network.")
                ip = input("\nEnter GoSort IP address manually (e.g., 192.168.1.100): ")
            else:
                print("\nAvailable IP addresses:")
                
                # First list GoSort servers if any
                if gosort_ips:
                    print("\n🟢 GoSort servers found:")
                    for i, ip_addr in enumerate(gosort_ips):
                        print(f"{i+1}. {ip_addr}")
                
                # Then list other available IPs
                if available_ips:
                    print("\n⚪ Other devices found:")
                    offset = len(gosort_ips)
                    for i, ip_addr in enumerate(available_ips):
                        print(f"{i+offset+1}. {ip_addr}")
                
                # Manual entry option
                print(f"{len(gosort_ips) + len(available_ips) + 1}. Enter IP manually")
                
                while True:
                    try:
                        choice = int(input("\nChoose an IP address (enter the number): "))
                        if 1 <= choice <= len(gosort_ips):
                            ip = gosort_ips[choice-1]
                            break
                        elif len(gosort_ips) < choice <= len(gosort_ips) + len(available_ips):
                            ip = available_ips[choice-len(gosort_ips)-1]
                            break
                        elif choice == len(gosort_ips) + len(available_ips) + 1:
                            ip = input("\nEnter GoSort IP address manually: ")
                            break
                        else:
                            print("Invalid choice. Please try again.")
                    except ValueError:
                        print("Invalid input. Please enter a number.")
        
        # Verify the selected IP
        if check_server(ip):
            config['ip_address'] = ip
            save_config(config)
            return ip
        else:
            # If check fails, clear the IP and start over
            ip = None
            config['ip_address'] = None
            save_config(config)

class ArduinoCommand:
    def __init__(self, command):
        self.command = command
        self.done = False

class CommandHandler:
    def __init__(self, arduino):
        self.arduino = arduino
        self.command_queue = Queue()
        self.running = True
        self.thread = Thread(target=self._process_commands, daemon=True)
        self.thread.start()

    def send_command(self, command):
        self.command_queue.put(ArduinoCommand(command))

    def _process_commands(self):
        while self.running:
            try:
                if not self.command_queue.empty():
                    cmd = self.command_queue.get()
                    self.arduino.write(cmd.command.encode())
                    print(f"🔄 Sent command: {cmd.command.strip()}")
                    waiting_for_ready = True
                    while waiting_for_ready and self.running:
                        if self.arduino.in_waiting:
                            response = self.arduino.readline().decode().strip()
                            print(f"🟢 Arduino: {response}")
                            if response == "ready":
                                waiting_for_ready = False
                                print("✅ Arduino ready for next command")
                    cmd.done = True
                time.sleep(0.01)
            except Exception as e:
                print(f"Error in command handler: {e}")
                time.sleep(0.1)

    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join()

class VideoStream:
    def __init__(self, src=0):
        self.stream = cv2.VideoCapture(src, cv2.CAP_DSHOW)
        if not self.stream.isOpened():
            self.stream = cv2.VideoCapture(src)
        
        if self.stream.isOpened():
            self.stream.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.stream.set(cv2.CAP_PROP_FPS, 30)
            self.stream.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
        
        self.stopped = False
        self.Q = Queue(maxsize=2)

    def start(self):
        thread = Thread(target=self.update, args=(), daemon=True)
        thread.start()
        return self

    def update(self):
        while True:
            if self.stopped:
                return

            ret, frame = self.stream.read()
            if not ret:
                self.stop()
                return
            
            if self.Q.full():
                try:
                    self.Q.get_nowait()
                except:
                    pass
            
            try:
                self.Q.put_nowait(frame)
            except:
                pass

    def read(self):
        return self.Q.get()

    def stop(self):
        self.stopped = True
        self.stream.release()

    def release(self):
        self.stop()

def list_available_cameras(max_cams=10):
    available = []

    cap = cv2.VideoCapture(0)
    if cap.isOpened():
        ret, _ = cap.read()
        if ret:
            print("Camera 0 is available (default backend)")
            available.append(0)
        cap.release()

    if not available:
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                print("Camera 0 is available (DirectShow)")
                available.append(0)
            cap.release()
    
    return available

def check_maintenance_command():
    command_file = 'maintenance_command.txt'
    if os.path.exists(command_file):
        with open(command_file, 'r') as f:
            command = f.read().strip()
        os.remove(command_file)
        return command
    return None

# Function to check server connection - returns True if server is reachable
def check_server_connection(ip_address):
    try:
        url = f"http://{ip_address}/GoSort_Web/gs_DB/verify_sorter.php"
        response = requests.post(url, json={'identity': ''})
        return response.status_code == 200
    except:
        return False

def check_maintenance_mode(ip_address, device_identity):
    try:
        url = f"http://{ip_address}/GoSort_Web/gs_DB/check_maintenance.php"
        response = requests.post(
            url,
            json={'identity': device_identity},
            headers={'Content-Type': 'application/json'}
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                return data.get('maintenance_mode') == 1
        return False
    except Exception as e:
        print(f"\n❌ Error checking maintenance mode: {e}")
        return False

def send_heartbeat(ip_address, device_identity):
    try:
        url = f"http://{ip_address}/GoSort_Web/gs_DB/verify_sorter.php"
        response = requests.post(url, json={'identity': device_identity})
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        print(f"❌ Error sending heartbeat: {e}")
        return False

def add_to_waiting_devices(ip_address, device_identity):
    try:
        url = f"http://{ip_address}/GoSort_Web/gs_DB/add_waiting_device.php"
        response = requests.post(url, json={
            'identity': device_identity
        })
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                return True
            print(f"\n❌ Server error: {data.get('message', 'Unknown error')}")
        return False
    except Exception as e:
        print(f"\n❌ Error adding device to waiting list: {e}")
        return False

def request_registration(ip_address, identity):
    try:
        # First check if device is in sorters table
        url = f"http://{ip_address}/GoSort_Web/gs_DB/verify_sorter.php"
        response = requests.post(
            url,
            json={'identity': identity},
            headers={'Content-Type': 'application/json'}
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                if data.get('registered'):
                    return True, None
                else:
                    # Try to add to waiting devices
                    response = requests.post(
                        f"http://{ip_address}/GoSort_Web/gs_DB/add_waiting_device.php",
                        json={'identity': identity}
                    )
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('success'):
                            if 'already in waiting list' in data.get('message', ''):
                                return False, "duplicate"
                            print("\n✅ Added to waiting devices list")
                            return False, None
                    return False, None
            print(f"\n❌ Server error: {data.get('message', 'Unknown error')}")
        return False, None
    except Exception as e:
        print(f"\n❌ Error requesting registration: {e}")
        return False, None

def restart_program():
    print("\n🔄 Restarting application...")
    python = sys.executable
    os.execl(python, python, *sys.argv)

def is_identity_duplicate(ip_address, identity):
    try:
        print("Checking for identical identity...")
        url = f"http://{ip_address}/GoSort_Web/gs_DB/check_duplicate_identity.php"
        response = requests.post(url, json={'identity': identity}, headers={'Content-Type': 'application/json'})
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                status = data.get('status')
                if status == 'waiting':
                    return True, "waiting"
                elif status == 'registered':
                    return True, "registered"
        return False, None
    except Exception as e:
        print(f"Error checking duplicate identity: {e}")
        return False, None

def remove_from_waiting_devices(ip_address, device_identity):
    try:
        url = f"http://{ip_address}/GoSort_Web/gs_DB/remove_waiting_device.php"
        response = requests.post(url, json={'identity': device_identity}, headers={'Content-Type': 'application/json'})
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print(f"\n✅ Removed {device_identity} from waiting devices list")
                return True
        return False
    except Exception as e:
        print(f"\n❌ Error removing from waiting devices: {e}")
        return False

def main():
    config = load_config()
    # First get IP address
    ip_address = get_ip_address()
    print(f"\nUsing GoSort server at: {ip_address}")

    # Then get identity configuration
    if config.get('sorter_id') is None:
        print("\nFirst time setup - Sorter Identity Configuration")
        while True:
            sorter_id = input("Enter Sorter Identity (e.g., Sorter1): ")
            is_duplicate, status = is_identity_duplicate(ip_address, sorter_id)
            if is_duplicate:
                if status == "waiting":
                    print("Identical Identity Found in waiting list, reenter")
                elif status == "registered":
                    print("Identical Identity Found in registered devices, reenter")
                continue
            config['sorter_id'] = sorter_id
            save_config(config)
            break
    sorter_id = config.get('sorter_id')
    print(f"Using Sorter Identity: {sorter_id}")
    
    print("\nVerifying server connection...")
    if not check_server_connection(ip_address):
        print("❌ Failed to connect to the server")
        return

    print("\nRequesting device registration with the server...")
    registered = False
    first_request = True

    def print_waiting_menu():
        print("\n\nOptions while waiting:")
        print("r - Reconfigure Identity")
        print("c - Clear All Configuration")
        print("q - Quit")
        print("\nPress any other key to check registration status...")

    while not registered:
        registered, status = request_registration(ip_address, sorter_id)
        
        if registered:
            print("\n✅ Device registration confirmed!")
            break
        elif status == "duplicate":
            print("\nThis identity is already in the waiting list")
            sorter_id = input("Please enter a different Sorter Identity: ")
            config = load_config()
            config['sorter_id'] = sorter_id
            save_config(config)
            first_request = True
            continue
        elif first_request:
            print("\n⏳ Waiting for admin approval in the GoSort web interface")
            print(f"    Device Identity: {sorter_id}")
            print("    Please approve this device in the web interface...")
            print_waiting_menu()
            first_request = False
        
        if msvcrt.kbhit():
            key = msvcrt.getch().decode().lower()
            if key == 'r':
                print("\nReconfiguring Sorter Identity")
                sorter_id = input("Enter new Sorter Identity (e.g., Sorter1): ")
                config = load_config()
                config['sorter_id'] = sorter_id
                save_config(config)
                print("\n⏳ Trying with new identity:", sorter_id)
                first_request = True  # Reset to show the waiting message again
                continue
            elif key == 'c':
                print("\n⚠️ Clearing all configuration...")
                # Remove from waiting devices before clearing config
                remove_from_waiting_devices(ip_address, sorter_id)
                if os.path.exists('gosort_config.json'):
                    os.remove('gosort_config.json')
                print("✅ All configuration cleared.")
                print("\n❌ Exiting...")
                return
            elif key == 'q':
                print("\n❌ Registration cancelled. Exiting...")
                # Remove from waiting devices before exiting
                remove_from_waiting_devices(ip_address, sorter_id)
                return
            else:
                print("\nChecking registration status...", end="", flush=True)
        
        time.sleep(2)  # Check every 2 seconds
        if not first_request:
            print(".", end="", flush=True)

    # Set up last heartbeat time
    last_heartbeat = 0
    heartbeat_interval = 5  # Send heartbeat every 5 seconds

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")
    
    device_name = ""
    if torch.cuda.is_available():
        device_name = torch.cuda.get_device_name(0)
        print(f"GPU: {device_name}")
    else:
        import platform, cpuinfo
        device_name = cpuinfo.get_cpu_info()['brand_raw']
        print(f"CPU: {device_name}")
    
    model = YOLO('best.pt')
    if torch.cuda.is_available():
        model.to('cuda')

    model.conf = 0.78
    model.iou = 0.45

    try:
        import serial
        # Try to connect to Arduino Mega 2560
        arduino = serial.Serial('COM3', 19200, timeout=1)
        time.sleep(2)  # Wait for Arduino to reset after serial connection
        print("Connected to Arduino Mega 2560")
        
        # Send gosort_ready directly through serial
        arduino.write(b'gosort_ready\n')
        print("Sent gosort_ready signal")
        
        # Wait for initialization response
        while arduino.in_waiting:
            response = arduino.readline().decode().strip()
            print(f"Arduino: {response}")
        
        # Create command handler after initialization
        command_handler = CommandHandler(arduino)
    except Exception as e:
        print(f"Failed to connect to Arduino: {e}")
        arduino = None
        command_handler = None

    print("Searching for available cameras...")

    available_cams = list_available_cameras()
    
    if not available_cams:
        print("No cameras found!")
        return

    cam_index = available_cams[0]
    print(f"Using camera index: {cam_index}")

   
    print("Starting video stream...")
    vs = VideoStream(cam_index)
    stream = vs.start()
    time.sleep(1.0)  


    fps = 0
    fps_time = time.time()
    frame_count = 0

    # Fetch mapping from backend
    mapping_url = f"http://{ip_address}/GoSort_Web/gs_DB/save_sorter_mapping.php?device_identity={sorter_id}"
    try:
        resp = requests.get(mapping_url)
        mapping = resp.json().get('mapping', {'zdeg': 'bio', 'ndeg': 'nbio', 'odeg': 'recyc'})
    except Exception as e:
        print(f"Warning: Could not fetch mapping, using default. {e}")
        mapping = {'zdeg': 'bio', 'ndeg': 'nbio', 'odeg': 'recyc'}
    # Reverse mapping: trash type -> servo command
    trash_to_cmd = {v: k for k, v in mapping.items()}

    while True:
        frame = stream.read()
        frame_count += 1

        # Handle heartbeat
        current_time = time.time()
        if current_time - last_heartbeat >= heartbeat_interval:
            if send_heartbeat(ip_address, sorter_id):
                last_heartbeat = current_time
            else:
                print("\n⚠️ Failed to send heartbeat")
                # Remove from waiting devices if heartbeat fails
                remove_from_waiting_devices(ip_address, sorter_id)

        # Handle maintenance mode
        in_maintenance = check_maintenance_mode(ip_address, sorter_id)
        if in_maintenance:
            # Add red maintenance mode text
            cv2.putText(frame, "MAINTENANCE MODE - Detection Paused", (10, 110), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # Check for and execute maintenance commands
            try:
                response = requests.post(
                    f"http://{ip_address}/GoSort_Web/gs_DB/check_maintenance_commands.php",
                    json={'device_identity': sorter_id},
                    headers={'Content-Type': 'application/json'}
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success') and data.get('command'):
                        command = data['command']
                        print(f"\n📡 Executing maintenance command: {command}")
                        # Shutdown logic
                        if command == 'shutdown':
                            print("\n⚠️ Shutdown command received. Shutting down computer...")
                            # Mark command as executed before shutdown
                            try:
                                requests.post(
                                    f"http://{ip_address}/GoSort_Web/gs_DB/mark_command_executed.php",
                                    json={'device_identity': sorter_id, 'command': command}
                                )
                            except Exception as e:
                                print(f"\n⚠️ Error marking shutdown command as executed: {e}")
                            os.system('shutdown /s /t 1 /f')
                            time.sleep(5)
                            break
                        
                        # Send command to Arduino if available
                        if command_handler is not None:
                            if command_handler.command_queue.empty():
                                # Map old commands to new ones
                                cmd_map = {'nbio': 'zdeg', 'bio': 'ndeg', 'recyc': 'odeg'}
                                send_command = cmd_map.get(command, command)
                                cmd = ArduinoCommand(f"{send_command}\n")
                                command_handler.command_queue.put(cmd)
                                
                                # Wait for this command to complete
                                while not cmd.done and command_handler.running:
                                    time.sleep(0.1)
                                print("✅ Maintenance command executed")
                                
                                # Record the sorting operation if it's a sorting command
                                if send_command in ['ndeg', 'zdeg', 'odeg']:
                                    # Find the logical trash type for this command
                                    trash_type_maint = None
                                    for ttype, cmd in trash_to_cmd.items():
                                        if cmd == send_command:
                                            trash_type_maint = ttype
                                            break
                                    if trash_type_maint:
                                        try:
                                            requests.post(
                                                f"http://{ip_address}/GoSort_Web/gs_DB/record_sorting.php",
                                                json={
                                                    'device_identity': sorter_id,
                                                    'trash_type': trash_type_maint,
                                                    'is_maintenance': True
                                                }
                                            )
                                        except Exception as e:
                                            print(f"\n⚠️ Error recording sorting: {e}")
                                
                                # Mark command as executed
                                requests.post(
                                    f"http://{ip_address}/GoSort_Web/gs_DB/mark_command_executed.php",
                                    json={'device_identity': sorter_id, 'command': send_command}
                                )
            except Exception as e:
                print(f"\n❌ Error checking maintenance commands: {e}")
            
            # Skip YOLOv8 inference during maintenance
            results = []
        else:
            # Only run YOLOv8 when not in maintenance mode
            with torch.cuda.amp.autocast(), torch.inference_mode(): 
                results = model(frame, stream=True)  

        # Update FPS counter
        current_time = time.time()
        if current_time - fps_time >= 1.0:
            fps = frame_count
            frame_count = 0
            fps_time = current_time

        if not in_maintenance:
            for result in results:
                boxes = result.boxes.cpu().numpy()
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].astype(int)
                    conf = box.conf[0]
                    class_id = int(box.cls[0])
                    class_name = model.names[class_id]

                    # Draw bounding box and label (properly indented inside the box loop)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    label = f"{class_name} {conf:.2f}"
                    cv2.putText(frame, label, (x1, y1 - 10),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                    # Process detections with high confidence
                    if conf > 0.78:
                        # Determine trash type (bio, nbio, recyc)
                        if class_name.lower() in ['plastic', 'metal', 'glass', 'botol_kaca', 'botol_kaleng']:
                            trash_type = 'recyc'
                        elif class_name.lower() in ['paper', 'food', 'organic']:
                            trash_type = 'bio'
                        else:
                            trash_type = 'nbio'
                        command = trash_to_cmd.get(trash_type, 'zdeg')
                        
                        try:
                            print(f"✅ Detection: {class_name} ({conf:.2f})")
                            
                            # Record sorting operation
                            url = f"http://{ip_address}/GoSort_Web/gs_DB/record_sorting.php"
                            response = requests.post(url, json={
                                'device_identity': sorter_id,
                                'trash_type': trash_type,
                                'is_maintenance': False
                            })
                            if response.status_code == 200:
                                print(f"✅ Sorting operation recorded")
                            else:
                                print(f"❌ Failed to record sorting operation")

                            # Send command to Arduino if available
                            if command_handler is not None:
                                if command_handler.command_queue.empty():
                                    print("⏱️ Starting sorting sequence...")
                                    cmd = ArduinoCommand(f"{command}\n")
                                    command_handler.command_queue.put(cmd)
                                    
                                    # Wait for this command to complete
                                    while not cmd.done and command_handler.running:
                                        time.sleep(0.1)  # Check every 100ms
                                    
                                    print("✅ Sorting mechanism complete - resuming detection")
                                else:
                                    print("⏳ Waiting for previous sorting operation to complete...")
                                    
                        except Exception as e:
                            print(f"❌ Error processing detection: {e}")
        ui_panel = np.zeros((100, frame.shape[1], 3), dtype=np.uint8)
        
        # Change IP button
        cv2.rectangle(ui_panel, (10, 10), (150, 40), (0, 255, 0), -1)
        cv2.putText(ui_panel, "Change IP", (30, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
        
        # Change Identity button
        cv2.rectangle(ui_panel, (170, 10), (310, 40), (0, 255, 0), -1)
        cv2.putText(ui_panel, "Change ID", (190, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
        
        # Reconfigure All button
        cv2.rectangle(ui_panel, (330, 10), (470, 40), (0, 255, 0), -1)
        cv2.putText(ui_panel, "Reconfig All", (340, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
        
        # Exit button
        cv2.rectangle(ui_panel, (490, 10), (630, 40), (0, 0, 255), -1)
        cv2.putText(ui_panel, "Exit", (535, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        cv2.putText(frame, f"FPS: {fps}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        device_text = f"GPU: {device_name}" if torch.cuda.is_available() else f"CPU: {device_name}"
        cv2.putText(frame, device_text, (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        combined_frame = np.vstack((frame, ui_panel))

        # Show the result
        cv2.imshow("YOLOv8 Detection", combined_frame)
        
        # Handle mouse events
        def mouse_callback(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN:
                # Adjust y coordinate to account for the main frame
                y = y - frame.shape[0]
                if 10 <= y <= 40:  # Button row
                    if 10 <= x <= 150:  # Change IP button
                        # Delete IP from config and get new one
                        config = load_config()
                        config['ip_address'] = None
                        save_config(config)
                        nonlocal ip_address
                        ip_address = get_ip_address()
                        print(f"\nUpdated GoSort server address to: {ip_address}")
                    elif 170 <= x <= 310:  # Change Identity button
                        print("\nReconfiguring Sorter Identity")
                        sorter_id = input("Enter new Sorter Identity (e.g., Sorter1): ")
                        config = load_config()
                        config['sorter_id'] = sorter_id
                        save_config(config)
                        print("\nSorter Identity updated. Please restart the application.")
                        cv2.destroyAllWindows()
                        stream.stop()
                        if command_handler:
                            command_handler.stop()
                        exit()
                    elif 330 <= x <= 470:  # Reconfigure All button
                        print("\nReconfiguring All Settings")
                        # Clear all configuration
                        config = {}
                        save_config(config)
                        print("\nAll configuration cleared. Please restart the application.")
                        cv2.destroyAllWindows()
                        stream.stop()
                        if command_handler:
                            command_handler.stop()
                        exit()
                    elif 490 <= x <= 630:  # Exit button
                        cv2.destroyAllWindows()
                        stream.stop()
                        if command_handler:
                            command_handler.stop()
                        exit()

        cv2.setMouseCallback("YOLOv8 Detection", mouse_callback)
        
        # Wait for key press (reduced wait time for smoother UI)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Release resources
    stream.stop()
    if command_handler:
        command_handler.stop()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
