import time
import requests
import json
import os
import socket
import concurrent.futures
import threading
import ipaddress
import msvcrt
import sys
from datetime import datetime

class ArduinoSimulator:
    def __init__(self):
        self.is_open = True
        self.in_waiting = False
        self.response_queue = []
        self.maintenance_mode = False
        
        # Simulated bin distances (cm)
        self.bin_distances = {
            'bio': 50,
            'nbio': 45,
            'recyc': 60,
            'mixed': 55
        }
        
        # Start bin fullness simulation thread
        self.running = True
        self.bin_thread = threading.Thread(target=self._simulate_bin_fullness)
        self.bin_thread.daemon = True
        self.bin_thread.start()

    def _simulate_bin_fullness(self):
        """Simulates gradual filling of bins"""
        while self.running:
            for bin_name in self.bin_distances:
                if self.bin_distances[bin_name] > 10:  # Don't let it get too full
                    self.bin_distances[bin_name] -= 1
                self.response_queue.append(f"bin_fullness:{bin_name}:{self.bin_distances[bin_name]}")
            time.sleep(30)  # Update every 30 seconds
            
    def adjust_bin_fullness(self, bin_name, distance):
        """Adjust bin fullness manually"""
        if bin_name in self.bin_distances:
            self.bin_distances[bin_name] = max(10, min(70, distance))  # Keep within 10-70cm range
            self.response_queue.append(f"bin_fullness:{bin_name}:{self.bin_distances[bin_name]}")
            return True
        return False
        
    def get_bin_fullness(self, bin_name):
        """Get bin fullness as a percentage"""
        if bin_name in self.bin_distances:
            distance = self.bin_distances[bin_name]
            return max(0, min(100, ((70 - distance) / 60) * 100))
        return 0
            
    def adjust_bin_fullness(self, bin_name, distance):
        """Adjust bin fullness manually"""
        if bin_name in self.bin_distances:
            self.bin_distances[bin_name] = max(10, min(70, distance))  # Keep within 10-70cm range
            self.response_queue.append(f"bin_fullness:{bin_name}:{self.bin_distances[bin_name]}")
            return True
        return False
        
    def get_bin_fullness(self, bin_name):
        """Get bin fullness as a percentage"""
        if bin_name in self.bin_distances:
            distance = self.bin_distances[bin_name]
            return max(0, min(100, ((70 - distance) / 60) * 100))
        return 0

    def write(self, data):
        data = data.decode().strip() if isinstance(data, bytes) else data.strip()
        
        # Simulate Arduino responses
        if data == 'gosort_ready':
            self.response_queue.append("GoSort Ready!")
        elif data == 'ping':
            self.response_queue.append("pong")
        elif data in ['zdeg', 'ndeg', 'odeg', 'mdeg']:
            self.response_queue.append(f"Moving servo to {data.upper()}")
            time.sleep(1)  # Simulate servo movement time
            self.response_queue.append(f"Moved to {data.upper()}")
        elif data == 'maintmode':
            self.maintenance_mode = True
            self.response_queue.append("Maintenance mode enabled")
        elif data == 'maintend':
            self.maintenance_mode = False
            self.response_queue.append("Maintenance mode disabled")
        elif data == 'unclog':
            self.response_queue.append("Unclogging mechanism activated")
            time.sleep(3)
            self.response_queue.append("Unclogging complete")
        elif data in ['sweep1', 'sweep2']:
            self.response_queue.append(f"Performing {data}")
            time.sleep(2)
            self.response_queue.append(f"{data} complete")

    def readline(self):
        if self.response_queue:
            self.in_waiting = bool(self.response_queue)
            return (self.response_queue.pop(0) + '\\n').encode()
        return b''

    def close(self):
        self.running = False
        self.is_open = False

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
        print(f"\\n❌ Error checking maintenance mode: {e}")
        return False

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
    print("\\nScanning network for available devices...")
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
            print(f"\\rScanning network... {progress:.1f}% complete", end="", flush=True)

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

    print("\\n\\nScan complete!")
    
    gosort_ips = sorted(list(set(gosort_ips)))
    available_ips = sorted(list(set(available_ips) - set(gosort_ips)))
    
    return gosort_ips, available_ips

def check_server(ip):
    print("\\rChecking server...", end="", flush=True)
    try:
        response = requests.get(f"http://{ip}/GoSort_Web/gs_DB/trash_detected.php", timeout=5)
        if response.status_code == 200 or (response.status_code == 400 and "No trash type provided" in response.text):
            print("\\r✅ Server connection successful!")
            return True
        print("\\r❌ GoSort does not exist in this server")
        return False
    except requests.exceptions.RequestException:
        print("\\r❌ GoSort does not exist in this server")
        return False

def get_ip_address():
    config = load_config()
    ip = config.get('ip_address')
    
    while True:
        if not ip:
            gosort_ips, available_ips = scan_network()
            
            if not gosort_ips and not available_ips:
                print("\\nNo devices found in the network.")
                ip = input("\\nEnter GoSort IP address manually (e.g., 192.168.1.100): ")
            else:
                print("\\nAvailable IP addresses:")
                if gosort_ips:
                    print("\\n🟢 GoSort servers found:")
                    for i, ip_addr in enumerate(gosort_ips):
                        print(f"{i+1}. {ip_addr}")
                
                if available_ips:
                    print("\\n⚪ Other devices found:")
                    offset = len(gosort_ips)
                    for i, ip_addr in enumerate(available_ips):
                        print(f"{i+offset+1}. {ip_addr}")
                print(f"{len(gosort_ips) + len(available_ips) + 1}. Enter IP manually")
                
                while True:
                    try:
                        choice = int(input("\\nChoose an IP address (enter the number): "))
                        if 1 <= choice <= len(gosort_ips):
                            ip = gosort_ips[choice-1]
                            break
                        elif len(gosort_ips) < choice <= len(gosort_ips) + len(available_ips):
                            ip = available_ips[choice-len(gosort_ips)-1]
                            break
                        elif choice == len(gosort_ips) + len(available_ips) + 1:
                            ip = input("\\nEnter GoSort IP address manually: ")
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

def process_bin_fullness(data, ip_address, device_identity):
    try:
        parts = data.split(':')
        if len(parts) == 3 and parts[0] == 'bin_fullness':
            bin_name = parts[1]
            distance = int(parts[2])
            
            try:
                response = requests.post(
                    f"http://{ip_address}/GoSort_Web/gs_DB/update_bin_fullness.php",
                    data={
                        'device_identity': device_identity,
                        'bin_name': bin_name,
                        'distance': distance
                    }
                )
                
                if response.status_code == 200 and "Record inserted" in response.text:
                    print(f"\\r✅ Bin Fullness - {bin_name}: {distance}cm (Saved to DB)", end="", flush=True)
                else:
                    print(f"\\r❌ Bin Fullness - {bin_name}: {distance}cm (DB Error: {response.text})", end="", flush=True)
            except Exception as e:
                print(f"\\r❌ Bin Fullness - {bin_name}: {distance}cm (Error: {e})", end="", flush=True)
                
    except Exception as e:
        print(f"\\nError processing bin fullness data: {e}")

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
                            print("\\n✅ Added to waiting devices list")
                            return False, None
                    return False, None
            print(f"\\n❌ Server error: {data.get('message', 'Unknown error')}")
        return False, None
    except Exception as e:
        print(f"\\n❌ Error requesting registration: {e}")
        return False, None

def remove_from_waiting_devices(ip_address, device_identity):
    try:
        url = f"http://{ip_address}/GoSort_Web/gs_DB/remove_waiting_device.php"
        response = requests.post(url, json={'identity': device_identity}, headers={'Content-Type': 'application/json'})
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print(f"\\n✅ Removed {device_identity} from waiting devices list")
                return True
        return False
    except Exception as e:
        print(f"\\n❌ Error removing from waiting devices: {e}")
        return False

def adjust_bin_fullness_menu(ser):
    """Show menu for adjusting bin fullness"""
    print("\nBin Fullness Adjustment Menu:")
    print("Current bin levels:")
    for bin_name, distance in ser.bin_distances.items():
        fullness = ser.get_bin_fullness(bin_name)
        print(f"{bin_name}: {fullness:.1f}% full (Distance: {distance}cm)")
    
    print("\nSelect bin to adjust:")
    for idx, bin_name in enumerate(ser.bin_distances.keys(), 1):
        print(f"{idx}. {bin_name}")
    print("b. Back to main menu")
    
    choice = input("\nEnter choice: ").lower()
    if choice == 'b':
        return
    
    try:
        idx = int(choice)
        if 1 <= idx <= len(ser.bin_distances):
            bin_name = list(ser.bin_distances.keys())[idx-1]
            try:
                new_distance = float(input(f"\nEnter new distance for {bin_name} (10-70cm): "))
                if ser.adjust_bin_fullness(bin_name, new_distance):
                    print(f"\n✅ Adjusted {bin_name} bin fullness")
                else:
                    print("\n❌ Failed to adjust bin fullness")
            except ValueError:
                print("\n❌ Invalid distance value")
    except ValueError:
        print("\n❌ Invalid choice")

def adjust_bin_fullness_menu(simulator):
    """Show menu for adjusting bin fullness"""
    print("\nBin Fullness Adjustment Menu:")
    print("Current bin levels:")
    for bin_name, distance in simulator.bin_distances.items():
        fullness = simulator.get_bin_fullness(bin_name)
        print(f"{bin_name}: {fullness:.1f}% full (Distance: {distance}cm)")
    
    print("\nSelect bin to adjust:")
    for idx, bin_name in enumerate(simulator.bin_distances.keys(), 1):
        print(f"{idx}. {bin_name}")
    print("b. Back to main menu")
    
    choice = input("\nEnter choice: ").lower()
    if choice == 'b':
        return
    
    try:
        idx = int(choice)
        if 1 <= idx <= len(simulator.bin_distances):
            bin_name = list(simulator.bin_distances.keys())[idx-1]
            try:
                new_distance = float(input(f"\nEnter new distance for {bin_name} (10-70cm): "))
                if simulator.adjust_bin_fullness(bin_name, new_distance):
                    print(f"\n✅ Adjusted {bin_name} bin fullness")
                else:
                    print("\n❌ Failed to adjust bin fullness")
            except ValueError:
                print("\n❌ Invalid distance value")
    except ValueError:
        print("\n❌ Invalid choice")

def main():
    print("🔄 Starting GoSort Simulation...")
    
    config = load_config()
    ip_address = get_ip_address()
    print(f"\nUsing GoSort server at: {ip_address}")

    if config.get('sorter_id') is None:
        print("\nFirst time setup - Sorter Identity Configuration")
        sorter_id = input("Enter Sorter Identity (e.g., Sorter1): ")
        config['sorter_id'] = sorter_id
        save_config(config)
    
    default_mapping = {
        'zdeg': 'bio',
        'ndeg': 'nbio',
        'odeg': 'recyc',
        'mdeg': 'mixed'
    }
    
    mapping_url = f"http://{ip_address}/GoSort_Web/gs_DB/save_sorter_mapping.php?device_identity={config['sorter_id']}"
    try:
        resp = requests.get(mapping_url)
        server_mapping = resp.json().get('mapping', {})
        mapping = default_mapping.copy()
        mapping.update(server_mapping)
    except Exception as e:
        print(f"Warning: Could not fetch mapping, using default. {e}")
        mapping = default_mapping

    menu_order = []
    if 'zdeg' in mapping:
        menu_order.append(('zdeg', mapping['zdeg']))
    if 'ndeg' in mapping:
        menu_order.append(('ndeg', mapping['ndeg']))
    if 'odeg' in mapping:
        menu_order.append(('odeg', mapping['odeg']))
    if 'mdeg' in mapping:
        menu_order.append(('mdeg', mapping['mdeg']))
        
    trash_labels = {
        'bio': 'Biodegradable',
        'nbio': 'Non-Biodegradable',
        'recyc': 'Hazardous',
        'mixed': 'Mixed Waste'
    }

    print("\\nRequesting device registration with the server...")
    registered = False
    first_request = True

    def print_waiting_menu():
        print("\\n\\nOptions while waiting:")
        print("r - Reconfigure Identity")
        print("a - Reconfigure All (IP and Identity)")
        print("q - Quit")
        print("\\nPress any other key to check registration status...")

    while not registered:
        registered, status = request_registration(ip_address, config['sorter_id'])
        
        if registered:
            print("\\n✅ Device registration confirmed!")
            break
        elif first_request:
            print("\\n⏳ Waiting for admin approval in the GoSort web interface")
            print(f"    Device Identity: {config['sorter_id']}")
            print("    Please approve this device in the web interface...")
            print_waiting_menu()
            first_request = False
        
        if msvcrt.kbhit():
            key = msvcrt.getch().decode().lower()
            if key == 'r':
                print("\\nReconfiguring Sorter Identity")
                sorter_id = input("Enter new Sorter Identity (e.g., Sorter1): ")
                config['sorter_id'] = sorter_id
                save_config(config)
                print("\\n⏳ Trying with new identity:", config['sorter_id'])
                first_request = True
                continue
            elif key == 'a':
                print("\\n⚙️ Reconfiguring All Settings...")
                remove_from_waiting_devices(ip_address, config['sorter_id'])
                config['ip_address'] = None
                config['sorter_id'] = None
                save_config(config)
                print("\\n✅ All configuration cleared. Please restart the application.")
                return
            elif key == 'q':
                print("\\n❌ Registration cancelled. Exiting...")
                remove_from_waiting_devices(ip_address, config['sorter_id'])
                return
            else:
                print("\\nChecking registration status...", end="", flush=True)
        
        time.sleep(2)
        if not first_request:
            print(".", end="", flush=True)

    print("\\n🔄 Initializing Arduino simulator...")
    ser = ArduinoSimulator()
    ser.write('gosort_ready\\n'.encode())
    time.sleep(0.1)
    
    while ser.in_waiting:
        response = ser.readline().decode().strip()
        if response:
            if response.startswith('bin_fullness:'):
                process_bin_fullness(response, ip_address, config['sorter_id'])
            else:
                print(f"🟢 Simulator Response: {response}")
    
    print("\\n✅ Simulator ready")
    
    arduino_connected = True
    
    def check_arduino_connection():
        return ser.is_open

    def print_menu(simulator):
        print("\nTrash Selection Menu:")
        for idx, (deg, ttype) in enumerate(menu_order, 1):
            label = trash_labels.get(ttype, ttype)
            # Get bin fullness for this type
            fullness = simulator.get_bin_fullness(ttype)
            print(f"{idx}. {label} [Fullness: {fullness:.1f}%]")
        print("4. Mixed")
        print("\nBin Controls:")
        print("f - Adjust bin fullness")
        print("\nSystem Controls:")
        print("r - Reconfigure IP")
        print("i - Reconfigure Identity")
        print("c - Clear All Configuration")
        print("q - Quit")
        
    print_menu(ser)
    last_maintenance_status = False
    check_interval = 1
    last_heartbeat = 0
    heartbeat_interval = 10

    while True:
        current_time = time.time()
        if current_time - last_heartbeat >= heartbeat_interval:
            if arduino_connected and check_arduino_connection():
                try:
                    while ser.in_waiting:
                        response = ser.readline().decode().strip()
                        if response:
                            if response.startswith('bin_fullness:'):
                                process_bin_fullness(response, ip_address, config['sorter_id'])
                            else:
                                print(f"\\n🟢 Simulator: {response}")
                    
                    requests.post(
                        f"http://{ip_address}/GoSort_Web/gs_DB/verify_sorter.php",
                        json={'identity': config['sorter_id']},
                        headers={'Content-Type': 'application/json'}
                    )
                    last_heartbeat = current_time
                except Exception as e:
                    print(f"\\n⚠️ Heartbeat error: {e}")
                    remove_from_waiting_devices(ip_address, config['sorter_id'])
            else:
                print("\\n⚠️ Simulator disconnected - stopping heartbeats")
                remove_from_waiting_devices(ip_address, config['sorter_id'])
                break

        current_maintenance = check_maintenance_mode(ip_address, config['sorter_id'])
        
        if current_maintenance != last_maintenance_status:
            if current_maintenance:
                print("\\n🔧 Entering maintenance mode - Controls disabled")
                print("Listening for maintenance commands...")
            else:
                print("\\n✅ Exiting maintenance mode - Controls enabled")
                try:
                    resp = requests.get(mapping_url)
                    mapping = resp.json().get('mapping', {'zdeg': 'bio', 'ndeg': 'nbio', 'odeg': 'recyc'})
                except Exception as e:
                    print(f"Warning: Could not fetch mapping, using default. {e}")
                    mapping = {'zdeg': 'bio', 'ndeg': 'nbio', 'odeg': 'recyc'}
                menu_order = [('zdeg', mapping['zdeg']), ('ndeg', mapping['ndeg']), ('odeg', mapping['odeg'])]
                print_menu(ser)
            last_maintenance_status = current_maintenance

        if current_maintenance:
            if not arduino_connected or not check_arduino_connection():
                print("\\n⚠️ Simulator disconnected - cannot execute maintenance commands")
                time.sleep(check_interval)
                continue
                
            try:
                response = requests.post(
                    f"http://{ip_address}/GoSort_Web/gs_DB/check_maintenance_commands.php",
                    json={'device_identity': config['sorter_id']},
                    headers={'Content-Type': 'application/json'}
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success') and data.get('command'):
                        command = data['command']
                        print(f"\\n📡 Received maintenance command from server: {command}")
                        
                        if command in ['unclog', 'sweep1', 'sweep2']:
                            print("Sending maintmode command to enable maintenance mode...")
                            ser.write("maintmode\\n".encode())
                            time.sleep(0.5)
                            
                            while ser.in_waiting:
                                response = ser.readline().decode().strip()
                                if response:
                                    print(f"🟢 Simulator Response: {response}")
                        
                        print(f"Sending to simulator: {command}")
                        ser.write(f"{command}\\n".encode())
                        
                        if command == 'unclog':
                            time.sleep(6)
                        elif command in ['sweep1', 'sweep2']:
                            time.sleep(5)
                        else:
                            time.sleep(0.1)
                        
                        while ser.in_waiting:
                            response = ser.readline().decode().strip()
                            if response:
                                print(f"🟢 Simulator Response: {response}")
                        
                        if command in ['unclog', 'sweep1', 'sweep2']:
                            print("Sending maintend command to exit maintenance mode...")
                            ser.write("maintend\\n".encode())
                            time.sleep(0.5)
                            
                            while ser.in_waiting:
                                response = ser.readline().decode().strip()
                                if response:
                                    print(f"🟢 Simulator Response: {response}")
                        
                        if command in ['ndeg', 'zdeg', 'odeg']:
                            trash_type = mapping.get(command)
                            if trash_type:
                                try:
                                    requests.post(
                                        f"http://{ip_address}/GoSort_Web/gs_DB/record_sorting.php",
                                        json={
                                            'device_identity': config['sorter_id'],
                                            'trash_type': trash_type,
                                            'is_maintenance': True
                                        }
                                    )
                                except Exception as e:
                                    print(f"\\n⚠️ Error recording sorting: {e}")
                        
                        requests.post(
                            f"http://{ip_address}/GoSort_Web/gs_DB/mark_command_executed.php",
                            json={'device_identity': config['sorter_id'], 'command': command}
                        )
                        
                        if command == 'shutdown':
                            print("\\n⚠️ Shutdown command received. Simulating shutdown...")
                            try:
                                requests.post(
                                    f"http://{ip_address}/GoSort_Web/gs_DB/mark_command_executed.php",
                                    json={'device_identity': config['sorter_id'], 'command': command}
                                )
                            except Exception as e:
                                print(f"\\n⚠️ Error marking shutdown command as executed: {e}")
                            break
            except Exception as e:
                print(f"\\n❌ Error checking maintenance commands: {e}")
            
            time.sleep(check_interval)
            continue

        if msvcrt.kbhit():
            choice = msvcrt.getch().decode().lower()
            
            if choice == 'q':
                break
            elif choice == 'r':
                config['ip_address'] = None
                save_config(config)
                print("\\nIP configuration reset. Please restart the application.")
                break
            elif choice == 'i':
                print("\\nReconfiguring Sorter Identity")
                sorter_id = input("Enter new Sorter Identity (e.g., Sorter1): ")
                config['sorter_id'] = sorter_id
                save_config(config)
                print("\\nSorter Identity updated. Please restart the application.")
                break
            elif choice == 'c':
                print("\\n⚠️ Clearing all configuration...")
                if os.path.exists('gosort_config.json'):
                    os.remove('gosort_config.json')
                print("✅ All configuration cleared. Please restart the application.")
                break
            elif choice in ['1', '2', '3', '4']:
                 idx = int(choice) - 1
                 if choice == '4':
                     command = 'mdeg'
                     trash_type = 'mixed'
                 else:
                     if idx >= len(menu_order):
                         print("Invalid choice.")
                         continue
                     trash_type = menu_order[idx][1]
                 command = None
                 for servo_key, ttype in mapping.items():
                     if ttype == trash_type:
                         command = servo_key
                         break
                 if not command:
                     command = 'zdeg'
                 ser.write(f"{command}\\n".encode())
                 print(f"\\n🔄 Moving to {command.upper()}...")
                 time.sleep(0.1)
                 while ser.in_waiting:
                     response = ser.readline().decode().strip()
                     if response:
                         print(f"🟢 Simulator Response: {response}")
                 
                 try:
                     requests.post(
                         f"http://{ip_address}/GoSort_Web/gs_DB/record_sorting.php",
                         json={
                             'device_identity': config['sorter_id'],
                             'trash_type': trash_type,
                             'is_maintenance': False
                         }
                     )
                 except Exception as e:
                     print(f"\n⚠️ Error recording sorting: {e}")
                 
                 print_menu(ser)
            elif choice == 'f':
                adjust_bin_fullness_menu(ser)
                print_menu(ser)
            elif choice not in ['\r', '\n']:
                print("\nInvalid choice. Please choose 1-4 for sorting, f for bin fullness, r for IP config, i for Identity config, or q to quit")
        
        time.sleep(0.1)
    
    ser.close()
    print("🔌 Simulation ended")

if __name__ == "__main__":
    main()