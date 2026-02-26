import os
import sys
import time
import json
import threading
import requests
import cv2
import numpy as np
import base64
import torch
from ultralytics import YOLO
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
    import socket
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
            response = requests.get(f"http://{ip}/GoSort_Web/gs_DB/trash_detected.php", timeout=0.5)
            if response.status_code == 200 or (
                response.status_code == 400 and "No trash type provided" in response.text
            ):
                gosort_ips.append(str(ip))
            else:
                available_ips.append(str(ip))
        except:
            pass
        update_progress()
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        executor.map(check_ip, network_ips)
    print("\n\nScan complete!")
    gosort_ips = sorted(list(set(gosort_ips)))
    available_ips = sorted(list(set(available_ips) - set(gosort_ips)))
    return gosort_ips, available_ips

def check_server(ip):
    print("\rChecking server...", end="", flush=True)
    try:
        response = requests.get(f"http://{ip}/GoSort_Web/gs_DB/trash_detected.php", timeout=5)
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
            gosort_ips, available_ips = scan_network()
            if not gosort_ips and not available_ips:
                print("\nNo devices found in the network.")
                ip = input("\nEnter GoSort IP address manually (e.g., 192.168.1.100): ")
            else:
                print("\nAvailable IP addresses:")
                if gosort_ips:
                    print("\n🟢 GoSort servers found:")
                    for i, ip_addr in enumerate(gosort_ips):
                        print(f"{i+1}. {ip_addr}")
                if available_ips:
                    print("\n⚪ Other devices found:")
                    offset = len(gosort_ips)
                    for i, ip_addr in enumerate(available_ips):
                        print(f"{i+offset+1}. {ip_addr}")
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
        if check_server(ip):
            config['ip_address'] = ip
            save_config(config)
            return ip
        else:
            ip = None
            config['ip_address'] = None
            save_config(config)

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

def play_sorting_audio(waste_type):
    if not PYGAME_AVAILABLE:
        return
    def play_audio_thread():
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
    import threading
    audio_thread = threading.Thread(target=play_audio_thread, daemon=True)
    audio_thread.start()

def get_poppins_font(font_size):
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
    try:
        return ImageFont.truetype("arial.ttf", font_size)
    except:
        return ImageFont.load_default()

def get_text_size_pil(text, font):
    if font is None:
        return (len(text) * 20, 30)
    try:
        bbox = font.getbbox(text)
        return (bbox[2] - bbox[0], bbox[3] - bbox[1])
    except:
        return (len(text) * 20, 30)

def draw_text_with_font(img, text, position, font_size, color, use_poppins=True):
    if PIL_AVAILABLE and use_poppins:
        try:
            font = get_poppins_font(font_size)
            img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(img_pil)
            color_rgb = (color[2], color[1], color[0])
            draw.text(position, text, font=font, fill=color_rgb)
            img = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
            return img
        except Exception as e:
            pass
    scale = font_size / 30.0
    cv2.putText(img, text, position, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2)
    return img

def draw_kiosk_ui(sorting_history, current_view='both', kiosk_width=1920, kiosk_height=1080):
    bg_color = (239, 243, 243)
    primary_green = (23, 74, 39)
    dark_gray = (55, 47, 31)
    medium_gray = (128, 114, 107)
    waste_colors = {
        'bio': (129, 185, 16),
        'nbio': (68, 68, 239),
        'hazardous': (11, 158, 245),
        'mixed': (128, 114, 107)
    }
    waste_names = {
        'bio': 'Biodegradable',
        'nbio': 'Non-Biodegradable',
        'hazardous': 'Hazardous',
        'mixed': 'Mixed'
    }
    kiosk_frame = np.full((kiosk_height, kiosk_width, 3), bg_color, dtype=np.uint8)
    header_height = 120
    cv2.rectangle(kiosk_frame, (0, 0), (kiosk_width, header_height), primary_green, -1)
    kiosk_frame = draw_text_with_font(kiosk_frame, "GoSort", (80, 40), 48, (255, 255, 255))
    view_text = "Press A+S to toggle views"
    kiosk_frame = draw_text_with_font(kiosk_frame, view_text, (kiosk_width - 300, 40), 20, (200, 200, 200))
    if not sorting_history:
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
        kiosk_frame = draw_text_with_font(kiosk_frame, no_items_text, (text_x, center_y), 36, medium_gray)
    else:
        last_item = sorting_history[0]
        waste_type = last_item.get('waste_type', 'nbio')
        waste_label = waste_names.get(waste_type, 'Unknown')
        color = waste_colors.get(waste_type, medium_gray)
        center_x = kiosk_width // 2
        center_y = kiosk_height // 2 - 50
        sorted_text = "Sorted:"
        font_large = get_poppins_font(60)
        sorted_width, _ = get_text_size_pil(sorted_text, font_large)
        waste_width, _ = get_text_size_pil(waste_label, font_large)
        if font_large is None:
            sorted_width = cv2.getTextSize(sorted_text, cv2.FONT_HERSHEY_SIMPLEX, 2.0, 3)[0][0]
            waste_width = cv2.getTextSize(waste_label, cv2.FONT_HERSHEY_SIMPLEX, 2.0, 3)[0][0]
        total_width = sorted_width + waste_width + 20
        start_x = center_x - total_width // 2
        kiosk_frame = draw_text_with_font(kiosk_frame, sorted_text, (start_x, center_y), 60, dark_gray)
        waste_x = start_x + sorted_width + 20
        kiosk_frame = draw_text_with_font(kiosk_frame, waste_label, (waste_x, center_y), 60, color)
        nice_day_y = center_y + 120
        nice_day_text = "Have a nice day"
        font_small = get_poppins_font(40)
        nice_day_width, _ = get_text_size_pil(nice_day_text, font_small)
        if font_small is None:
            nice_day_width = cv2.getTextSize(nice_day_text, cv2.FONT_HERSHEY_SIMPLEX, 1.3, 2)[0][0]
        nice_day_x = center_x - nice_day_width // 2
        kiosk_frame = draw_text_with_font(kiosk_frame, nice_day_text, (nice_day_x, nice_day_y), 40, medium_gray)
    return kiosk_frame

def map_category_to_command(waste_type, mapping):
    waste_type = waste_type.lower()
    for cmd, typ in mapping.items():
        if typ.lower() == waste_type:
            return cmd
    default_commands = {
        'bio': 'zdeg',
        'nbio': 'ndeg',
        'hazardous': 'odeg',
        'mixed': 'mdeg'
    }
    return default_commands.get(waste_type, 'ndeg')

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

def request_registration(ip_address, identity):
    try:
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

def main():
    config = load_config()
    ip_address = get_ip_address()
    config['ip_address'] = ip_address
    save_config(config)
    print(f"\nUsing GoSort server at: {ip_address}")
    sorting_history = []
    current_view = 'kiosk'
    a_key_pressed = False
    a_key_time = 0
    kiosk_maximized = False
    if config.get('sorter_id') is None:
        print("\nFirst time setup - Sorter Identity Configuration")
        sorter_id = input("Enter Sorter Identity (e.g., Sorter1): ")
        config['sorter_id'] = sorter_id
        save_config(config)
    sorter_id = config.get('sorter_id')
    print(f"Using Sorter Identity: {sorter_id}")
    print("\nVerifying server connection...")
    if not send_heartbeat(ip_address, sorter_id):
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
    import msvcrt
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
                first_request = True
                continue
            elif key == 'c':
                print("\n⚠️ Clearing all configuration...")
                if os.path.exists('gosort_config.json'):
                    os.remove('gosort_config.json')
                print("✅ All configuration cleared.")
                print("\n❌ Exiting...")
                return
            elif key == 'q':
                print("\n❌ Registration cancelled. Exiting...")
                return
            else:
                print("\nChecking registration status...", end="", flush=True)
        time.sleep(2)
        if not first_request:
            print(".", end="", flush=True)
    last_heartbeat = 0
    heartbeat_interval = 5
    last_maintenance_status = False
    check_interval = 1
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
    if device_mode == 'gpu' and torch.cuda.is_available():
        device = torch.device('cuda')
        backend = 'CUDA (NVIDIA GPU)'
    else:
        device = torch.device('cpu')
        backend = 'CPU'
    print(f"Using device: {device}")
    print(f"Backend: {backend}")
    device_name = ""
    if device.type == 'cuda':
        device_name = torch.cuda.get_device_name(0)
        print(f"GPU: {device_name}")
    else:
        import cpuinfo
        device_name = cpuinfo.get_cpu_info()['brand_raw']
        print(f"CPU: {device_name}")
    model = YOLO('best885.pt')
    if device.type == 'cuda':
        model.to('cuda')
    model.conf = 0.50
    model.iou = 0.50
    print("Searching for available cameras...")
    available_cams = list_available_cameras()
    if not available_cams:
        print("No cameras found!")
        return
    cam_index = available_cams[0]
    print(f"Using camera index: {cam_index}")
    print("Starting video stream...")
    cap = cv2.VideoCapture(cam_index)
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
        ret, frame = cap.read()
        if not ret:
            print("Failed to read from camera. Exiting...")
            break
        frame_count += 1
        current_time = time.time()
        if current_time - last_heartbeat >= heartbeat_interval:
            if send_heartbeat(ip_address, sorter_id):
                last_heartbeat = current_time
            else:
                print("\n Failed to send heartbeat")
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
            cv2.putText(frame, "MAINTENANCE MODE - Detection Paused", (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            results = []
        else:
            results = model.predict(frame, stream=False)
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
                    categories = load_categories()
                    class_name = None
                    for category, items in categories.items():
                        if detected_item.lower() in [item.lower() for item in items]:
                            class_name = category
                            break
                    if class_name is None:
                        class_name = "nbio"
                    clean_frame = frame.copy()
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f"{detected_item} {conf:.2f}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                    if conf > 0.50:
                        command = map_category_to_command(class_name, mapping)
                        trash_type = mapping.get(command, 'nbio')
                        try:
                            print(f"✅ Detection: {detected_item} ({conf:.2f}) - Category: {class_name}")
                            _, buffer = cv2.imencode('.jpg', clean_frame)
                            image_base64 = base64.b64encode(buffer).decode('utf-8')
                            detected_classes = [detected_item]
                            trash_class_str = ', '.join(detected_classes)
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
                                timestamp = datetime.now().strftime("%H:%M:%S")
                                sorting_history.insert(0, {
                                    'waste_type': trash_type,
                                    'item_name': detected_item,
                                    'timestamp': timestamp,
                                    'confidence': float(conf)
                                })
                                if len(sorting_history) > 20:
                                    sorting_history.pop()
                                play_sorting_audio(trash_type)
                            else:
                                print(f"❌ Failed to record sorting operation")
                        except Exception as e:
                            print(f"❌ Error processing detection: {e}")
        ui_panel = np.zeros((100, frame.shape[1], 3), dtype=np.uint8)
        cv2.rectangle(ui_panel, (10, 10), (150, 40), (0, 255, 0), -1)
        cv2.putText(ui_panel, "Change IP", (30, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
        cv2.rectangle(ui_panel, (170, 10), (310, 40), (0, 255, 0), -1)
        cv2.putText(ui_panel, "Change ID", (190, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
        cv2.rectangle(ui_panel, (330, 10), (470, 40), (0, 255, 0), -1)
        cv2.putText(ui_panel, "Reconfig All", (340, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
        cv2.rectangle(ui_panel, (490, 10), (630, 40), (0, 0, 255), -1)
        cv2.putText(ui_panel, "Exit", (535, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"FPS: {fps}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        device_text = f"GPU: {device_name}" if torch.cuda.is_available() else f"CPU: {device_name}"
        cv2.putText(frame, device_text, (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        view_text = f"View: {current_view.upper()} (Press A+S to toggle)"
        text_size = cv2.getTextSize(view_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0]
        text_x = frame.shape[1] - text_size[0] - 10
        cv2.putText(frame, view_text, (text_x, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        combined_frame = np.vstack((frame, ui_panel))
        if current_view == 'both' or current_view == 'camera':
            cv2.imshow("YOLOv11 Detection", combined_frame)
        else:
            try:
                cv2.destroyWindow("YOLOv11 Detection")
            except cv2.error:
                pass
        if current_view == 'both' or current_view == 'kiosk':
            kiosk_frame = draw_kiosk_ui(sorting_history, current_view)
            cv2.namedWindow("GoSort Kiosk - Sorting Display", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("GoSort Kiosk - Sorting Display", 1920, 1080)
            cv2.imshow("GoSort Kiosk - Sorting Display", kiosk_frame)
            if not kiosk_maximized:
                try:
                    time.sleep(0.1)
                    import platform
                    if platform.system() == 'Windows':
                        import ctypes
                        hwnd = ctypes.windll.user32.FindWindowW(None, "GoSort Kiosk - Sorting Display")
                        if hwnd:
                            ctypes.windll.user32.ShowWindow(hwnd, 3)
                    else:
                        cv2.setWindowProperty("GoSort Kiosk - Sorting Display", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                    kiosk_maximized = True
                except Exception as e:
                    cv2.resizeWindow("GoSort Kiosk - Sorting Display", 1920, 1080)
                    kiosk_maximized = True
        else:
            try:
                cv2.destroyWindow("GoSort Kiosk - Sorting Display")
            except cv2.error:
                pass
        def mouse_callback(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN:
                y = y - frame.shape[0]
                if 10 <= y <= 40:
                    if 10 <= x <= 150:
                        config = load_config()
                        config['ip_address'] = None
                        save_config(config)
                        nonlocal ip_address
                        ip_address = get_ip_address()
                        print(f"\nUpdated GoSort server address to: {ip_address}")
                    elif 170 <= x <= 310:
                        print("\nReconfiguring Sorter Identity")
                        sorter_id = input("Enter new Sorter Identity (e.g., Sorter1): ")
                        config = load_config()
                        config['sorter_id'] = sorter_id
                        save_config(config)
                        print("\nSorter Identity updated. Please restart the application.")
                        cv2.destroyAllWindows()
                        cap.release()
                        exit()
                    elif 330 <= x <= 470:
                        print("\nReconfiguring All Settings")
                        config = {}
                        save_config(config)
                        print("\nAll configuration cleared. Please restart the application.")
                        cv2.destroyAllWindows()
                        cap.release()
                        exit()
                    elif 490 <= x <= 630:
                        cv2.destroyAllWindows()
                        cap.release()
                        exit()
        if current_view == 'both' or current_view == 'camera':
            try:
                cv2.setMouseCallback("YOLOv11 Detection", mouse_callback)
            except cv2.error:
                pass
        key = cv2.waitKey(1) & 0xFF
        if key == ord('a') or key == ord('A'):
            a_key_pressed = True
            a_key_time = time.time()
        if (key == ord('s') or key == ord('S')) and a_key_pressed:
            if time.time() - a_key_time < 0.5:
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
        if a_key_pressed and time.time() - a_key_time > 0.5:
            a_key_pressed = False
        if key == ord('q') or key == 27:
            print("\n👋 Exiting application...")
            break
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
