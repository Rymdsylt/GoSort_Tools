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

class ArduinoSimulator:
    def __init__(self):
        self.last_command = None
        print("🤖 Arduino Simulator initialized")
    
    def write(self, data):
        command = data.decode().strip()
        self.last_command = command
        return len(data)
    
    def readline(self):
        if self.last_command == 'gosort_ready\n':
            return b'GoSort Arduino Simulator Ready!\n'
        elif self.last_command in ['nbio\n', 'bio\n', 'recyc\n']:
            return f'Moving servo to {self.last_command.strip()} position\n'.encode()
        return b''
    
    @property
    def in_waiting(self):
        return self.last_command is not None
    
    def close(self):
        print("🤖 Arduino Simulator disconnected")
    
    def reset_input_buffer(self):
        self.last_command = None

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
    
    # Get sorter identity if not set
    if config.get('sorter_id') is None:
        print("\nFirst time setup - Sorter Identity Configuration")
        sorter_id = input("Enter Sorter Identity (e.g., Sorter1): ")
        config['sorter_id'] = sorter_id
        save_config(config)
    
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
                    if add_to_waiting_devices(ip_address, identity):
                        print("\n✅ Added to waiting devices list")
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

def main():
    print("\n🤖 Starting GoSort Simulation")
    print("This is a simulation version that doesn't require Arduino hardware")
    
    config = load_config()
    
    # First time setup - ask for both identity and IP
    if config.get('sorter_id') is None or config.get('ip_address') is None:
        print("\nFirst time setup - Configuration")
        if config.get('sorter_id') is None:
            sorter_id = input("Enter Sorter Identity (e.g., Sorter1): ")
            config['sorter_id'] = sorter_id
            save_config(config)
    
    ip_address = get_ip_address()
    print(f"\nUsing GoSort server at: {ip_address}")
    
    print("\nRequesting device registration with the server...")
    registered = False
    first_request = True

    def print_waiting_menu():
        print("\n\nOptions while waiting:")
        print("r - Reconfigure Identity")
        print("a - Reconfigure All (IP and Identity)")
        print("q - Quit")
        print("\nPress any other key to check registration status...")

    while not registered:
        registered, _ = request_registration(ip_address, config['sorter_id'])
        
        if registered:
            print("\n✅ Device registration confirmed!")
            break
        elif first_request:
            print("\n⏳ Waiting for admin approval in the GoSort web interface")
            print(f"    Device Identity: {config['sorter_id']}")
            print("    Please approve this device in the web interface...")
            print_waiting_menu()
            first_request = False
        
        if msvcrt.kbhit():
            key = msvcrt.getch().decode().lower()
            if key == 'r':
                print("\nReconfiguring Sorter Identity")
                sorter_id = input("Enter new Sorter Identity (e.g., Sorter1): ")
                config['sorter_id'] = sorter_id
                save_config(config)
                print("\n⏳ Trying with new identity:", config['sorter_id'])
                first_request = True
                continue
            elif key == 'a':
                print("\n⚙️ Reconfiguring All Settings...")
                config['ip_address'] = None
                config['sorter_id'] = None
                save_config(config)
                print("\n✅ All configuration cleared. Please restart the application.")
                return
            elif key == 'q':
                print("\n❌ Registration cancelled. Exiting...")
                return
            else:
                print("\nChecking registration status...", end="", flush=True)
        
        time.sleep(2)
        if not first_request:
            print(".", end="", flush=True)
    
    # Initialize Arduino simulator
    ser = ArduinoSimulator()
    ser.write('gosort_ready\n'.encode())
    time.sleep(0.1)
    
    while ser.in_waiting:
        response = ser.readline().decode().strip()
        if response:
            print(f"🤖 Simulator Response: {response}")
    
    print("\n✅ Simulator initialized and ready")
    
    def print_menu():
        print("\nTrash Selection Menu:")
        print("1. Non Bio")
        print("2. Bio")
        print("3. Recyclable")
        print("r. Reconfigure IP")
        print("i. Reconfigure Identity")
        print("c. Clear All Configuration")
        print("q. Quit")

    print_menu()
    last_maintenance_status = False
    check_interval = 1
    last_heartbeat = 0
    heartbeat_interval = 10

    while True:
        current_time = time.time()
        if current_time - last_heartbeat >= heartbeat_interval:
            try:
                requests.post(
                    f"http://{ip_address}/GoSort_Web/gs_DB/verify_sorter.php",
                    json={'identity': config['sorter_id']},
                    headers={'Content-Type': 'application/json'}
                )
                last_heartbeat = current_time
            except Exception as e:
                print(f"\n⚠️ Heartbeat error: {e}")

        current_maintenance = check_maintenance_mode(ip_address, config['sorter_id'])
        
        if current_maintenance != last_maintenance_status:
            if current_maintenance:
                print("\n🔧 Entering maintenance mode - Controls disabled")
                print("Listening for maintenance commands...")
            else:
                print("\n✅ Exiting maintenance mode - Controls enabled")
                print_menu()
            last_maintenance_status = current_maintenance

        if current_maintenance:
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
                        print(f"\n📡 Executing maintenance command: {command}")
                        ser.write(f"{command}\n".encode())
                        time.sleep(0.1)
                        
                        while ser.in_waiting:
                            response = ser.readline().decode().strip()
                            if response:
                                print(f"🤖 Simulator Response: {response}")
                        
                        if command in ['bio', 'nbio', 'recyc']:
                            try:
                                requests.post(
                                    f"http://{ip_address}/GoSort_Web/gs_DB/record_sorting.php",
                                    json={
                                        'device_identity': config['sorter_id'],
                                        'trash_type': command,
                                        'is_maintenance': True
                                    }
                                )
                            except Exception as e:
                                print(f"\n⚠️ Error recording sorting: {e}")
                        
                        requests.post(
                            f"http://{ip_address}/GoSort_Web/gs_DB/mark_command_executed.php",
                            json={'device_identity': config['sorter_id'], 'command': command}
                        )
            except Exception as e:
                print(f"\n❌ Error checking maintenance commands: {e}")
            
            time.sleep(check_interval)
            continue

        if msvcrt.kbhit():
            choice = msvcrt.getch().decode().lower()
            
            if choice == 'q':
                break
            elif choice == 'r':
                config = load_config()
                config['ip_address'] = None
                save_config(config)
                print("\nIP configuration reset. Please restart the application.")
                break
            elif choice == 'i':
                config = load_config()
                print("\nReconfiguring Sorter Identity")
                sorter_id = input("Enter new Sorter Identity (e.g., Sorter1): ")
                config['sorter_id'] = sorter_id
                save_config(config)
                print("\nSorter Identity updated. Please restart the application.")
                break
            elif choice == 'c':
                print("\n⚠️ Clearing all configuration...")
                if os.path.exists('gosort_config.json'):
                    os.remove('gosort_config.json')
                print("✅ All configuration cleared. Please restart the application.")
                break
            elif choice in ['1', '2', '3']:
                command = {
                    '1': 'nbio',
                    '2': 'bio',
                    '3': 'recyc'
                }[choice]
                ser.write(f"{command}\n".encode())
                print(f"\n🔄 Simulating movement to {command.upper()}...")
                time.sleep(0.1)
                while ser.in_waiting:
                    response = ser.readline().decode().strip()
                    if response:
                        print(f"🤖 Simulator Response: {response}")
                
                try:
                    requests.post(
                        f"http://{ip_address}/GoSort_Web/gs_DB/record_sorting.php",
                        json={
                            'device_identity': config['sorter_id'],
                            'trash_type': command,
                            'is_maintenance': False
                        }
                    )
                except Exception as e:
                    print(f"\n⚠️ Error recording sorting: {e}")
                
                print_menu()
            elif choice not in ['\r', '\n']:
                print("\nInvalid choice. Please choose 1, 2, 3, r for IP config, i for Identity config, or q to quit")
        
        time.sleep(0.1)
    
    ser.close()
    print("🔌 Simulator disconnected")

if __name__ == "__main__":
    main()
