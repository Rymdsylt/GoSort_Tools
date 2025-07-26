import time
import requests
import json
import os
import socket
import concurrent.futures
import threading

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
    gosort_ips = sorted(list(set(gosort_ips)))
    available_ips = sorted(list(set(available_ips) - set(gosort_ips)))
    
    return gosort_ips, available_ips

def check_server(ip):
    print("\rChecking server...", end="", flush=True)
    try:
        # Try the new path first
        response = requests.get(f"http://{ip}/GoSort_Web/gs_DB/trash_detected.php", timeout=5)
        if response.status_code == 200 or (response.status_code == 400 and "No trash type provided" in response.text):
            print("\r✅ Server connection successful!")
            return True
            
        # If that fails, try the legacy path
        response = requests.get(f"http://{ip}/GoSort/gs_DB/trash_detected.php", timeout=5)
        if response.status_code == 200 or (response.status_code == 400 and "No trash type provided" in response.text):
            print("\r✅ Server connection successful!")
            return True
            
        print("\r❌ GoSort does not exist in this server")
        return False
    except requests.exceptions.RequestException:
        print("\r❌ GoSort does not exist in this server")
        return False

def check_maintenance_command():
    command_file = 'maintenance_command.txt'
    if os.path.exists(command_file):
        with open(command_file, 'r') as f:
            command = f.read().strip()
        os.remove(command_file)
        return command
    return None

def get_or_create_auth_token(ip_address):
    token_file = 'python_auth_token.txt'
    if os.path.exists(token_file):
        with open(token_file, 'r') as f:
            return f.read().strip()
    
    try:
        url = f"http://{ip_address}/GoSort_Web/gs_DB/connection_status.php"
        response = requests.post(url, data={'token': ''})
        if os.path.exists(token_file):
            with open(token_file, 'r') as f:
                return f.read().strip()
    except:
        pass
    return None

def send_heartbeat(ip_address, auth_token, device_identity):
    try:
        url = f"http://{ip_address}/GoSort_Web/gs_DB/connection_status.php"
        response = requests.post(url, json={
            'token': auth_token,
            'identity': device_identity
        })
        if response.status_code != 200:
            print(f"❌ Error sending heartbeat: {response.status_code}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Error sending heartbeat: {e}")
        return False

def request_registration(ip_address, identity):
    try:
        url = f"http://{ip_address}/GoSort_Web/gs_DB/request_registration.php"
        response = requests.post(
            url,
            json={'identity': identity},
            headers={'Content-Type': 'application/json'}
        )
        if response.status_code == 200:
            return True
        return False
    except Exception as e:
        print(f"❌ Error requesting registration: {e}")
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

class SimulatedArduino:
    def __init__(self):
        self.last_command = None

    def simulate_movement(self, trash_type):
        print(f"🔄 Simulating servo movement for {trash_type}")
        time.sleep(1)
        print("✅ Movement complete")
        print("ready")

def main():
    ip_address = get_ip_address()
    print(f"\nUsing GoSort server at: {ip_address}")
    
    config = load_config()
    sorter_id = config.get('sorter_id')
    
    # Get authentication token
    auth_token = get_or_create_auth_token(ip_address)
    if not auth_token:
        print("❌ Failed to get authentication token")
        return

    # Request registration if needed
    if not request_registration(ip_address, sorter_id):
        print("❌ Failed to register device")
        return
        
    print("\n✅ Connected to Simulated Arduino")
    print("\nTrash Selection Menu:")
    print("1. Non Bio")
    print("2. Bio")
    print("3. Recyclable")
    print("r. Reconfigure IP")
    print("q. Quit")
    
    simulated_arduino = SimulatedArduino()
    
    while True:
        choice = input("\nChoose option (1-3, r for IP config, q to quit): ")
        
        choice = choice.lower()
        if choice == 'q':
            break
            
        if choice == 'r':
            config = load_config()
            config['ip_address'] = None
            save_config(config)
            ip_address = get_ip_address()
            print(f"\nUpdated GoSort server address to: {ip_address}")
            continue
        
        if choice in ['1', '2', '3']:
            serial_data = {
                '1': 'nbio',
                '2': 'bio',
                '3': 'recyc'
            }
            trash_type = serial_data[choice]
            simulated_arduino.simulate_movement(trash_type)

            try:
                url = f"http://{ip_address}/GoSort_Web/gs_DB/trash_detected.php"
                response = requests.get(url, params={'type': trash_type})
                if response.status_code == 200:
                    print("✅ Detection recorded in database")
                else:
                    print(f"❌ Failed to record detection in database: {response.text}")
                    print(f"Status code: {response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"❌ Error connecting to server: {e}")
        else:
            print("Invalid choice. Please choose 1, 2, or 3")
    
    print("🔌 Simulation ended")

if __name__ == "__main__":
    main()
