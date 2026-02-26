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
import base64
import socket
import concurrent.futures
import threading
import sys
import msvcrt
import platform
import cpuinfo
from datetime import datetime
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import pygame
    PYGAME_AVAILABLE = True
    pygame.mixer.init()
except ImportError:
    PYGAME_AVAILABLE = False

def is_maintenance_mode():
    return os.path.exists('python_maintenance_mode.txt')

def load_categories():
    categories_file = 'categories.json'
    if os.path.exists(categories_file):
        with open(categories_file, 'r') as f:
            return json.load(f)
    return {}

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
    
    print("Scanning for available cameras...")
    
    # Try each camera index
    for i in range(max_cams):
        found = False
        
        # Try default backend first
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None and frame.size > 0:
                print(f"✅ Camera {i} is available (default backend)")
                available.append(i)
                found = True
            cap.release()
        
        # If not found with default, try DirectShow (Windows)
        if not found:
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None and frame.size > 0:
                    print(f"✅ Camera {i} is available (DirectShow)")
                    available.append(i)
                    found = True
                cap.release()
        
        # Small delay to avoid resource conflicts
        time.sleep(0.1)
    
    if available:
        print(f"\n🎥 Found {len(available)} camera(s): {available}")
    else:
        print("\n❌ No cameras found!")
    
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

def map_category_to_command(waste_type, mapping):
    # waste_type is already a category like 'bio', 'nbio', 'hazardous', 'mixed'
    # Convert to lowercase for comparison
    waste_type = waste_type.lower()
    
    # Find the servo command for this waste type from the mapping
    for cmd, typ in mapping.items():
        if typ.lower() == waste_type:
            return cmd
    
    # Default commands if not found in mapping
    default_commands = {
        'bio': 'zdeg',
        'nbio': 'ndeg',
        'hazardous': 'odeg',
        'mixed': 'mdeg'
    }
    return default_commands.get(waste_type, 'ndeg')  # Default to ndeg if no mapping found

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
                return data.get('maintenance_mode') == 11
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

def list_arduino_ports():
    """Return a list of candidate serial port device names likely to be Arduinos."""
    try:
        import serial.tools.list_ports
        ports = serial.tools.list_ports.comports()
        candidates = []
        for port in ports:
            if 'Arduino' in port.description or '2560' in port.description or 'Mega' in port.description:
                print(f"Found Arduino-like device at: {port.device} ({port.description})")
                candidates.append(port.device)
        # If none matched by description, return all ports as fallback
        if not candidates:
            for port in ports:
                candidates.append(port.device)
        return candidates
    except Exception:
        return []

def connect_to_arduino(port):
    """Try to open a serial connection to the provided port with safe options.

    Returns an open Serial object or None on failure.
    """
    try:
        import serial
        # Attempt quick open/close to release lock if possible
        try:
            temp_ser = serial.Serial(port)
            temp_ser.close()
        except Exception:
            pass

        ser = serial.Serial(
            port=port,
            baudrate=115200,
            timeout=1,
            write_timeout=1,
            # exclusive param may not exist on all platforms/pyserial versions
        )
        time.sleep(2)
        try:
            ser.reset_input_buffer()
        except Exception:
            pass
        return ser
    except Exception as e:
        print(f"Error connecting to {port}: {e}")
        return None

def process_bin_fullness(data, ip_address, device_identity):
    # Format is "bin_fullness:BinName:Distance"
    try:
        parts = data.split(':')
        if len(parts) == 3 and parts[0] == 'bin_fullness':
            bin_name = parts[1]
            try:
                distance = int(parts[2])
            except Exception:
                distance = parts[2]

            # Send data to backend using form data
            try:
                response = requests.post(
                    f"http://{ip_address}/GoSort_Web/gs_DB/update_bin_fullness.php",
                    data={
                        'device_identity': device_identity,
                        'bin_name': bin_name,
                        'distance': distance
                    },
                    timeout=5
                )

                if response.status_code == 200 and "Record inserted" in response.text:
                    print(f"\r✅ Bin Fullness - {bin_name}: {distance}cm (Saved to DB)", end="", flush=True)
                else:
                    print(f"\r❌ Bin Fullness - {bin_name}: {distance}cm (DB Error: {response.text})", end="", flush=True)
            except Exception as e:
                print(f"\r❌ Bin Fullness - {bin_name}: {distance}cm (Error: {e})", end="", flush=True)
    except Exception as e:
        print(f"\nError processing bin fullness data: {e}")

def play_sorting_audio(waste_type):
    """Play audio file based on waste type in a separate thread (non-blocking)"""
    if not PYGAME_AVAILABLE:
        return
    
    def play_audio_thread():
        # Map waste types to audio files
        audio_files = {
            'bio': 'audio/biodegradable.mp3',
            'nbio': 'audio/nonbiodegradable.mp3',
            'hazardous': 'audio/hazardous.mp3',
            'mixed': 'audio/mixed.mp3'
        }
        
        audio_file = audio_files.get(waste_type)
        if audio_file and os.path.exists(audio_file):
            try:
                pygame.mixer.music.load(audio_file)
                pygame.mixer.music.play()
            except Exception as e:
                print(f"\n⚠️ Error playing audio: {e}")
    
    # Start audio in a separate thread so it doesn't block UI updates
    audio_thread = Thread(target=play_audio_thread, daemon=True)
    audio_thread.start()

def get_poppins_font(font_size):
    """Try to load Poppins font, return None if not available"""
    if not PIL_AVAILABLE:
        return None
    
    font_paths = [
        'fonts/Poppins-Regular.ttf',
        'fonts/Poppins-SemiBold.ttf',
        'C:/Windows/Fonts/poppins.ttf',
        'C:/Windows/Fonts/Poppins-Regular.ttf',
    ]
    
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, font_size)
            except:
                continue
    
    # Try system default sans-serif
    try:
        return ImageFont.truetype("arial.ttf", font_size)
    except:
        return ImageFont.load_default()
    
def get_text_size_pil(text, font):
    """Get text size using PIL font"""
    if font is None:
        return (len(text) * 20, 30)  # Rough estimate
    try:
        bbox = font.getbbox(text)
        return (bbox[2] - bbox[0], bbox[3] - bbox[1])
    except:
        return (len(text) * 20, 30)
    
def draw_text_with_font(img, text, position, font_size, color, use_poppins=True):
    """Draw text with Poppins font if available, otherwise use OpenCV default"""
    if PIL_AVAILABLE and use_poppins:
        try:
            font = get_poppins_font(font_size)
            
            # Convert OpenCV image to PIL
            img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(img_pil)
            
            # Draw text - convert BGR to RGB for PIL
            color_rgb = (color[2], color[1], color[0])
            draw.text(position, text, font=font, fill=color_rgb)
            
            # Convert back to OpenCV format
            img = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
            return img
        except Exception as e:
            # Fallback to OpenCV if PIL fails
            pass
    
    # Fallback to OpenCV font
    scale = font_size / 30.0
    cv2.putText(img, text, position, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2)
    return img

def draw_kiosk_ui(sorting_history, current_view='both', kiosk_width=1920, kiosk_height=1080):
    """Create a simplified kiosk-style UI showing only the last sorted item"""
    # Webapp color scheme (BGR format for OpenCV)
    bg_color = (239, 243, 243)  # #F3F3EF - app background
    primary_green = (23, 74, 39)  # #274a17 - primary green
    dark_gray = (55, 47, 31)  # #1f2937 - dark gray text
    medium_gray = (128, 114, 107)  # #6b7280 - medium gray
    
    # Waste type colors (BGR format)
    waste_colors = {
        'bio': (129, 185, 16),  # #10b981 - green
        'nbio': (68, 68, 239),  # #ef4444 - red
        'hazardous': (11, 158, 245),  # #f59e0b - orange/amber
        'mixed': (128, 114, 107)  # #6b7280 - gray
    }
    
    # Simplified waste names
    waste_names = {
        'bio': 'Biodegradable',
        'nbio': 'Non-Biodegradable',
        'hazardous': 'Hazardous',
        'mixed': 'Mixed'
    }
    
    # Create background with webapp color
    kiosk_frame = np.full((kiosk_height, kiosk_width, 3), bg_color, dtype=np.uint8)
    
    # Simple header
    header_height = 120
    cv2.rectangle(kiosk_frame, (0, 0), (kiosk_width, header_height), primary_green, -1)
    
    # GoSort title
    kiosk_frame = draw_text_with_font(kiosk_frame, "GoSort", 
                                      (80, 40), 48, (255, 255, 255))
    
    # View mode indicator (top right, subtle)
    view_text = "Press A+S to toggle views"
    kiosk_frame = draw_text_with_font(kiosk_frame, view_text, 
                                      (kiosk_width - 300, 40), 20, (200, 200, 200))
    
    # Display only the last sorted item
    if not sorting_history:
        # Show "No items sorted yet" message
        center_x = kiosk_width // 2
        center_y = kiosk_height // 2
        no_items_text = "No items sorted yet"
        font = get_poppins_font(36)
        if font:
            text_width, _ = get_text_size_pil(no_items_text, font)
            text_x = center_x - text_width // 2
        else:
            text_size = cv2.getTextSize(no_items_text, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 2)[0]
            text_x = center_x - text_size[0] // 2
        kiosk_frame = draw_text_with_font(kiosk_frame, no_items_text, 
                                         (text_x, center_y), 36, medium_gray)
    else:
        # Get the most recent (first) item
        last_item = sorting_history[0]
        waste_type = last_item.get('waste_type', 'nbio')
        waste_label = waste_names.get(waste_type, 'Unknown')
        color = waste_colors.get(waste_type, medium_gray)
        
        # Center the content
        center_x = kiosk_width // 2
        center_y = kiosk_height // 2 - 50
        
        # "Sorted:" text
        sorted_text = "Sorted:"
        font_large = get_poppins_font(60)
        
        # Calculate text widths
        sorted_width, _ = get_text_size_pil(sorted_text, font_large)
        waste_width, _ = get_text_size_pil(waste_label, font_large)
        
        # If using OpenCV fallback, estimate width
        if font_large is None:
            sorted_width = cv2.getTextSize(sorted_text, cv2.FONT_HERSHEY_SIMPLEX, 2.0, 3)[0][0]
            waste_width = cv2.getTextSize(waste_label, cv2.FONT_HERSHEY_SIMPLEX, 2.0, 3)[0][0]
        
        # Calculate starting position to center both texts together
        total_width = sorted_width + waste_width + 20  # 20px spacing
        start_x = center_x - total_width // 2
        
        # Draw "Sorted:" text
        kiosk_frame = draw_text_with_font(kiosk_frame, sorted_text, 
                                         (start_x, center_y), 60, dark_gray)
        
        # Draw waste type text in color (next to "Sorted:")
        waste_x = start_x + sorted_width + 20
        kiosk_frame = draw_text_with_font(kiosk_frame, waste_label, 
                                         (waste_x, center_y), 60, color)
        
        # "Have a nice day" message below
        nice_day_y = center_y + 120
        nice_day_text = "Have a nice day"
        font_small = get_poppins_font(40)
        nice_day_width, _ = get_text_size_pil(nice_day_text, font_small)
        
        if font_small is None:
            nice_day_width = cv2.getTextSize(nice_day_text, cv2.FONT_HERSHEY_SIMPLEX, 1.3, 2)[0][0]
        
        nice_day_x = center_x - nice_day_width // 2
        kiosk_frame = draw_text_with_font(kiosk_frame, nice_day_text, 
                                         (nice_day_x, nice_day_y), 40, medium_gray)
    
    return kiosk_frame

def main():
    config = load_config()
    # First get IP address
    ip_address = get_ip_address()
    config['ip_address'] = ip_address
    save_config(config)
    print(f"\nUsing GoSort server at: {ip_address}")
    
    # Initialize sorting history for kiosk UI
    sorting_history = []
    
    # View toggle state: 'both', 'camera', or 'kiosk'
    current_view = 'kiosk'  # Start with kiosk view visible
    a_key_pressed = False
    a_key_time = 0
    kiosk_maximized = False  # Track if kiosk window has been maximized

    # Then get identity configuration
    if config.get('sorter_id') is None:
        print("\nFirst time setup - Sorter Identity Configuration")
        sorter_id = input("Enter Sorter Identity (e.g., Sorter1): ")
        config['sorter_id'] = sorter_id
        save_config(config)
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

    # Track maintenance status for change detection
    last_maintenance_status = False
    check_interval = 1  # Check maintenance mode every second

    # Device mode selection (CPU/GPU)
    if config.get('device_mode') is None:
        print("\nDevice Mode Configuration")
        gpu_available = torch.cuda.is_available()
        if gpu_available:
            print("Select device mode:")
            print("1. GPU (CUDA)")
            print("2. CPU")
            while True:
                choice = input("Enter 1 for GPU or 2 for CPU: ").strip()
                if choice == '1':
                    config['device_mode'] = 'gpu'
                    break
                elif choice == '2':
                    config['device_mode'] = 'cpu'
                    break
                else:
                    print("Invalid input. Please enter 1 or 2.")
        else:
            print("No GPU detected. Defaulting to CPU mode.")
            config['device_mode'] = 'cpu'
        save_config(config)
    device_mode = config.get('device_mode')
    print(f"Using device mode: {device_mode.upper()}")

    # Use device_mode from config to set torch.device
    if device_mode == 'gpu' and torch.cuda.is_available():
        device = torch.device('cuda')
        backend = 'CUDA (NVIDIA GPU)'
    else:
        # No CUDA available or CPU explicitly selected -> use CPU
        device = torch.device('cpu')
        backend = 'CPU'
    print(f"Using device: {device}")
    print(f"Backend: {backend}")
    
    device_name = ""
    if device.type == 'cuda':
        device_name = torch.cuda.get_device_name(0)
        print(f"GPU: {device_name}")
    elif 'DirectML' in backend:
        device_name = 'Integrated Graphics (DirectML)'
        print(f"Integrated Graphics: {device_name}")
    else:
        device_name = cpuinfo.get_cpu_info()['brand_raw']
        print(f"CPU: {device_name}")
    
    model = YOLO('best885.pt')
    if device.type == 'cuda':
        model.to('cuda')
    else:
        # model remains on CPU by default
        pass

    model.conf = 0.50  
    model.iou = 0.50   

    try:
        import serial
        arduino = None
        command_handler = None
        arduino_connected = False
        candidate_ports = list_arduino_ports()
        for p in candidate_ports:
            ser = connect_to_arduino(p)
            if ser is None:
                continue
            try:
                arduino = ser
                print(f"Connected to Arduino on {p}")
                # Signal readiness to Arduino and read any initial messages
                try:
                    arduino.write(b'gosort_ready\n')
                except Exception:
                    pass
                time.sleep(0.2)
                while getattr(arduino, 'in_waiting', 0):
                    try:
                        response = arduino.readline().decode().strip()
                        if response:
                            print(f"Arduino: {response}")
                            if response.startswith('bin_fullness:'):
                                process_bin_fullness(response, ip_address, sorter_id)
                    except Exception:
                        break

                command_handler = CommandHandler(arduino)
                arduino_connected = True

                def check_arduino_connection():
                    nonlocal arduino_connected
                    try:
                        if not arduino or not getattr(arduino, 'is_open', True):
                            arduino_connected = False
                            return False
                        arduino.write(b'ping\n')
                        time.sleep(0.1)
                        return True
                    except Exception as e:
                        print(f"\n❌ Arduino connection lost: {e}")
                        arduino_connected = False
                        return False

                break
            except Exception as e:
                print(f"Failed to initialize serial on {p}: {e}")
                try:
                    ser.close()
                except Exception:
                    pass
                arduino = None
        if not arduino_connected:
            print("No Arduino found on any COM port.")
            def check_arduino_connection():
                return False
    except Exception as e:
        print(f"Error during Arduino port search: {e}")
        arduino = None
        command_handler = None
        arduino_connected = False
        def check_arduino_connection():
            return False

    print("Searching for available cameras...")

    available_cams = list_available_cameras()
    
    if not available_cams:
        print("No cameras found!")
        return

    cam_index = available_cams[0]
    current_cam_idx = 0  # Index into available_cams list
    print(f"Using camera index: {cam_index}")

   
    print("Starting video stream...")
    vs = VideoStream(cam_index)
    stream = vs.start()
    time.sleep(1.0)  


    fps = 0
    fps_time = time.time()
    frame_count = 0


    mapping_url = f"http://{ip_address}/GoSort_Web/gs_DB/save_sorter_mapping.php?device_identity={sorter_id}"
    try:
        resp = requests.get(mapping_url)
        mapping = resp.json().get('mapping', {'zdeg': 'bio', 'ndeg': 'nbio', 'odeg': 'hazardous'})
    except Exception as e:
        print(f"Warning: Could not fetch mapping, using default. {e}")
        mapping = {'zdeg': 'bio', 'ndeg': 'nbio', 'odeg': 'hazardous'}

    trash_to_cmd = {v: k for k, v in mapping.items()}

    while True:
        frame = stream.read()
        frame_count += 1
        

        current_time = time.time()
        if current_time - last_heartbeat >= heartbeat_interval:

            if arduino_connected and check_arduino_connection():
                if send_heartbeat(ip_address, sorter_id):
                    last_heartbeat = current_time
                else:
                    print("\n Failed to send heartbeat")
                 
                    remove_from_waiting_devices(ip_address, sorter_id)
            else:
          
                print("\n Arduino disconnected - stopping heartbeats")

                remove_from_waiting_devices(ip_address, sorter_id)
                break

        # Process any incoming serial messages (bin fullness, logs, etc.)
        try:
            if arduino_connected and command_handler is not None and getattr(command_handler.arduino, 'in_waiting', 0):
                while command_handler.arduino.in_waiting:
                    try:
                        line = command_handler.arduino.readline().decode().strip()
                        if not line:
                            continue
                        if line.startswith('bin_fullness:'):
                            process_bin_fullness(line, ip_address, sorter_id)
                        else:
                            print(f"🟢 Arduino: {line}")
                    except Exception:
                        break
        except Exception:
            pass


        current_maintenance = check_maintenance_mode(ip_address, sorter_id)
        

        if current_maintenance != last_maintenance_status:
            if current_maintenance:
                print("\n Entering maintenance mode - Detection paused")
                print("Listening for maintenance commands...")
            else:
                print("\n Exiting maintenance mode - Detection resumed")

                try:
                    resp = requests.get(mapping_url)
                    mapping = resp.json().get('mapping', {'zdeg': 'bio', 'ndeg': 'nbio', 'odeg': 'hazardous'})
                except Exception as e:
                    print(f"Warning: Could not fetch mapping, using default. {e}")
                    mapping = {'zdeg': 'bio', 'ndeg': 'nbio', 'odeg': 'hazardous'}

                trash_to_cmd = {v: k for k, v in mapping.items()}
            last_maintenance_status = current_maintenance

        if current_maintenance:

            cv2.putText(frame, "MAINTENANCE MODE - Detection Paused", (10, 110), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            

            if not arduino_connected or not check_arduino_connection():
                print("\n Arduino disconnected - cannot execute maintenance commands")

                results = []
            else:
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
                            print(f"\n📡 Received maintenance command from server: {command}")
                            print(f"Current mapping: {mapping}")
                            
              
                            if command == 'shutdown':
                                print("\n⚠️ Shutdown command received. Shutting down computer...")
            
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
                            
              
                            if command_handler is not None:
                                if command_handler.command_queue.empty():

                                    if command in ['unclog', 'sweep1', 'sweep2']:
                                        print("Sending maintmode command to enable maintenance mode...")
                                        command_handler.arduino.write("maintmode\n".encode())
                                        time.sleep(0.5) 
                                        
                                        while command_handler.arduino.in_waiting:
                                            response = command_handler.arduino.readline().decode().strip()
                                            if response:
                                                print(f" Arduino Response: {response}")
                                
                                    print(f"Sending to Arduino: {command}")
                                    command_handler.arduino.write(f"{command}\n".encode())
                                    
                      
                                    if command == 'unclog':
                                        time.sleep(6) 
                                    elif command in ['sweep1', 'sweep2']:
                                        time.sleep(5)
                                    else:
                                        time.sleep(0.1)
                                    
                                    while command_handler.arduino.in_waiting:
                                        response = command_handler.arduino.readline().decode().strip()
                                        if response:
                                            print(f"Arduino Response: {response}")
                                    
                             
                                    if command in ['unclog', 'sweep1', 'sweep2']:
                                        print("Sending maintend command to exit maintenance mode...")
                                        command_handler.arduino.write("maintend\n".encode())
                                        time.sleep(0.5) 
                                        
                                        while command_handler.arduino.in_waiting:
                                            response = command_handler.arduino.readline().decode().strip()
                                            if response:
                                                print(f"🟢 Arduino Response: {response}")
                                    
                                 
                                    if command in ['ndeg', 'zdeg', 'odeg']:
                                        # Find the trash type for this servo command using mapping
                                        trash_type = mapping.get(command)
                                        if trash_type:
                                            try:
                                                requests.post(
                                                    f"http://{ip_address}/GoSort_Web/gs_DB/record_sorting.php",
                                                    json={
                                                        'device_identity': sorter_id,
                                                        'trash_type': trash_type,
                                                        'is_maintenance': True
                                                    }
                                                )
                                                # Add to sorting history for kiosk UI FIRST (so UI updates immediately)
                                                timestamp = datetime.now().strftime("%H:%M:%S")
                                                sorting_history.insert(0, {
                                                    'waste_type': trash_type,
                                                    'item_name': 'Maintenance Sort',
                                                    'timestamp': timestamp,
                                                    'confidence': 1.0
                                                })
                                                # Keep only last 20 items
                                                if len(sorting_history) > 20:
                                                    sorting_history.pop()
                                                
                                                # Play audio for the sorted waste type (non-blocking)
                                                play_sorting_audio(trash_type)
                                            except Exception as e:
                                                print(f"\n⚠️ Error recording sorting: {e}")
                                    
                                    # Mark command as executed
                                    requests.post(
                                        f"http://{ip_address}/GoSort_Web/gs_DB/mark_command_executed.php",
                                        json={'device_identity': sorter_id, 'command': command}
                                    )
                except Exception as e:
                    print(f"\n❌ Error checking maintenance commands: {e}")
            
            # Skip YOLOv8 inference during maintenance
            results = []
        else:
            # Only run YOLOv8 when not in maintenance mode
            # Use model.predict(frame, stream=False) to avoid PyTorch version_counter errors
            results = model.predict(frame, stream=False)

        # Update FPS counter
        current_time = time.time()
        if current_time - fps_time >= 1.0:
            fps = frame_count
            frame_count = 0
            fps_time = current_time

        if not current_maintenance:
            for result in results:
                boxes = result.boxes.cpu().numpy()
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].astype(int)
                    conf = box.conf[0]
                    class_id = int(box.cls[0])
                    detected_item = model.names[class_id]
                    
                    # Map the detected item to its category using categories.json
                    categories = load_categories()
                    class_name = None
                    for category, items in categories.items():
                        if detected_item.lower() in [item.lower() for item in items]:
                            class_name = category
                            break
                    
                    if class_name is None:
                        class_name = "nbio"  # Default category if not found

                    # Store original frame for database
                    clean_frame = frame.copy()

                    # Draw bounding box and label with 75% opacity (only for display)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f"{detected_item} {conf:.2f}", (x1, y1 - 10),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                    # Process detections with high confidence
                    if conf > 0.50:  # 50% confidence threshold
                        # Map the detected category to a servo command
                        command = map_category_to_command(class_name, mapping)
                        # Get the corresponding trash type from the mapping
                        trash_type = mapping.get(command, 'nbio')
                        
                        try:
                            print(f"✅ Detection: {detected_item} ({conf:.2f}) - Category: {class_name}")
                            
                            # Convert clean frame to base64 for sending
                            _, buffer = cv2.imencode('.jpg', clean_frame)
                            image_base64 = base64.b64encode(buffer).decode('utf-8')
                            
                            # For mixed waste, we'll collect all detected items
                            detected_classes = []
                            if trash_type == 'mixed':
                                # Look for other detections in this frame
                                for other_box in boxes:
                                    other_conf = other_box.conf[0]
                                    if other_conf > 0.50:  # Use same confidence threshold
                                        other_class_id = int(other_box.cls[0])
                                        other_item = model.names[other_class_id]
                                        detected_classes.append(other_item)
                            else:
                                detected_classes = [detected_item]
                            
                            # Join the detected classes with commas
                            trash_class_str = ', '.join(detected_classes)
                            
                            # Record sorting operation
                            url = f"http://{ip_address}/GoSort_Web/gs_DB/record_sorting.php"
                            response = requests.post(url, json={
                                'device_identity': sorter_id,
                                'trash_type': trash_type,
                                'trash_class': trash_class_str,
                                'confidence': float(conf),
                                'image_data': image_base64,
                                'is_maintenance': False
                            })
                            if response.status_code == 200:
                                print(f"✅ Sorting operation recorded")
                                
                                # Add to sorting history for kiosk UI FIRST (so UI updates immediately)
                                timestamp = datetime.now().strftime("%H:%M:%S")
                                sorting_history.insert(0, {
                                    'waste_type': trash_type,
                                    'item_name': detected_item,
                                    'timestamp': timestamp,
                                    'confidence': float(conf)
                                })
                                # Keep only last 20 items
                                if len(sorting_history) > 20:
                                    sorting_history.pop()
                                
                                # Play audio for the sorted waste type (non-blocking)
                                play_sorting_audio(trash_type)
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
        
        # Switch Camera button
        cv2.rectangle(ui_panel, (330, 10), (490, 40), (100, 200, 255), -1)  # Orange color
        camera_label = f"Camera ({current_cam_idx + 1}/{len(available_cams)})"
        cv2.putText(ui_panel, camera_label, (345, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        
        # Reconfigure All button
        cv2.rectangle(ui_panel, (510, 10), (650, 40), (0, 255, 0), -1)
        cv2.putText(ui_panel, "Reconfig All", (520, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
        
        # Exit button
        cv2.rectangle(ui_panel, (670, 10), (810, 40), (0, 0, 255), -1)
        cv2.putText(ui_panel, "Exit", (715, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
        cv2.putText(frame, f"FPS: {fps}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        device_text = f"GPU: {device_name}" if torch.cuda.is_available() else f"CPU: {device_name}"
        cv2.putText(frame, device_text, (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Display current view mode
        view_text = f"View: {current_view.upper()} (Press A+S to toggle)"
        text_size = cv2.getTextSize(view_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0]
        text_x = frame.shape[1] - text_size[0] - 10
        cv2.putText(frame, view_text, (text_x, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        
        combined_frame = np.vstack((frame, ui_panel))

        # Show/hide windows based on current view mode
        if current_view == 'both' or current_view == 'camera':
            cv2.imshow("YOLOv11 Detection", combined_frame)
        else:
            try:
                cv2.destroyWindow("YOLOv11 Detection")
            except cv2.error:
                pass  # Window doesn't exist, ignore
        
        if current_view == 'both' or current_view == 'kiosk':
            kiosk_frame = draw_kiosk_ui(sorting_history, current_view)
            cv2.namedWindow("GoSort Kiosk - Sorting Display", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("GoSort Kiosk - Sorting Display", 1920, 1080)
            cv2.imshow("GoSort Kiosk - Sorting Display", kiosk_frame)
            
            # Maximize kiosk window on first display
            if not kiosk_maximized:
                try:
                    # Small delay to ensure window is created
                    time.sleep(0.1)
                    # Try to maximize using Windows API if on Windows
                    if platform.system() == 'Windows':
                        import ctypes
                        hwnd = ctypes.windll.user32.FindWindowW(None, "GoSort Kiosk - Sorting Display")
                        if hwnd:
                            # SW_MAXIMIZE = 3
                            ctypes.windll.user32.ShowWindow(hwnd, 3)
                    else:
                        # On other platforms, use fullscreen mode
                        cv2.setWindowProperty("GoSort Kiosk - Sorting Display", 
                                            cv2.WND_PROP_FULLSCREEN, 
                                            cv2.WINDOW_FULLSCREEN)
                    kiosk_maximized = True
                except Exception as e:
                    # Fallback: set to a large size
                    cv2.resizeWindow("GoSort Kiosk - Sorting Display", 1920, 1080)
                    kiosk_maximized = True
        else:
            try:
                cv2.destroyWindow("GoSort Kiosk - Sorting Display")
            except cv2.error:
                pass  # Window doesn't exist, ignore
        
        # Handle mouse events
        def mouse_callback(event, x, y, flags, param):
            nonlocal current_cam_idx, stream, ip_address
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
                    elif 330 <= x <= 490:  # Switch Camera button
                        if len(available_cams) > 1:
                            print("\n🔄 Switching camera...")
                            stream.stop()
                            current_cam_idx = (current_cam_idx + 1) % len(available_cams)
                            cam_index = available_cams[current_cam_idx]
                            print(f"Switched to camera {current_cam_idx + 1}/{len(available_cams)} (Index: {cam_index})")
                            # Restart video stream with new camera
                            stream = VideoStream(cam_index).start()
                            time.sleep(1.0)
                        else:
                            print("\n⚠️ Only one camera available")
                    elif 510 <= x <= 650:  # Reconfigure All button
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
                    elif 670 <= x <= 810:  # Exit button
                        cv2.destroyAllWindows()
                        stream.stop()
                        if command_handler:
                            command_handler.stop()
                        exit()

        # Set mouse callback only if camera window is visible
        if current_view == 'both' or current_view == 'camera':
            try:
                cv2.setMouseCallback("YOLOv11 Detection", mouse_callback)
            except cv2.error:
                pass  # Window doesn't exist, ignore
        
        # Handle keyboard input - check for A+S hotkey
        key = cv2.waitKey(1) & 0xFF
        
        # Check for 'a' or 'A' key
        if key == ord('a') or key == ord('A'):
            a_key_pressed = True
            a_key_time = time.time()
        
        # Check for 's' or 'S' key (after 'a' was pressed)
        if (key == ord('s') or key == ord('S')) and a_key_pressed:
            # Check if 'a' was pressed recently (within 0.5 seconds)
            if time.time() - a_key_time < 0.5:
                # Toggle view mode
                if current_view == 'both':
                    current_view = 'camera'
                    print("\n🔄 Switched to Camera view only (Press A+S to toggle)")
                elif current_view == 'camera':
                    current_view = 'kiosk'
                    print("\n🔄 Switched to Kiosk view only (Press A+S to toggle)")
                elif current_view == 'kiosk':
                    current_view = 'both'
                    print("\n🔄 Switched to Both views (Press A+S to toggle)")
            a_key_pressed = False
        
        # Reset 'a' key flag if too much time has passed
        if a_key_pressed and time.time() - a_key_time > 0.5:
            a_key_pressed = False
        
        # Quit on 'q' or ESC key
        if key == ord('q') or key == 27:  # 27 is ESC key
            print("\n👋 Exiting application...")
            break

    # Release resources
    stream.stop()
    if command_handler:
        command_handler.stop()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
