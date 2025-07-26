import serial
import serial.tools.list_ports
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

def list_arduino_ports():
    ports = serial.tools.list_ports.comports()
    mega_ports = []
    
    for port in ports:
        if 'Arduino' in port.description or '2560' in port.description:
            print(f"Found Arduino Mega at: {port.device}")
            mega_ports.append(port.device)
    
    return mega_ports

def connect_to_arduino(port):
    try:
        try:
            temp_ser = serial.Serial(port)
            temp_ser.close()
        except:
            pass

        ser = serial.Serial(
            port=port,
            baudrate=19200,
            timeout=1,
            write_timeout=1,
            exclusive=True
        )
        time.sleep(3) 
        ser.reset_input_buffer()
        return ser
    except serial.SerialException as e:
        if 'PermissionError' in str(e):
            print(f"Error: Port {port} is being used by another program.")
            print("Close any other programs using it (e.g., Arduino IDE).")
        else:
            print(f"Error connecting to {port}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error while connecting to {port}: {e}")
        return None

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
    
    # First heartbeat will create the token on the server
    try:
        url = f"http://{ip_address}/GoSort_Web/gs_DB/connection_status.php"
        response = requests.post(url, data={'token': ''})
        if os.path.exists(token_file):  # Server should have created the token
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
            if response.status_code == 401:  # Token invalid or expired
                return False
            print(f"❌ Failed to send heartbeat: {response.text}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Error sending heartbeat: {e}")
        return False

def request_registration(ip_address, identity):
    try:
        # First check if the device is already registered
        url = f"http://{ip_address}/GoSort_Web/gs_DB/request_registration.php"
        response = requests.post(
            url,
            json={'identity': identity},
            headers={'Content-Type': 'application/json'}
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                if data.get('registered'):
                    # Device is already registered, store the token
                    token = data.get('token')
                    with open('python_auth_token.txt', 'w') as f:
                        f.write(token)
                    return True, token
                # Not registered yet, keep waiting
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
    # First get IP address
    config = load_config()
    ip_address = get_ip_address()
    print(f"\nUsing GoSort server at: {ip_address}")
    
    # Then get or set identity
    config = load_config()
    if config.get('sorter_id') is None:
        print("\nFirst time setup - Sorter Identity Configuration")
        sorter_id = input("Enter Sorter Identity (e.g., Sorter1): ")
        config['sorter_id'] = sorter_id
        save_config(config)
    
    print("\nRequesting device registration with the server...")
    dots_thread = None

    def print_waiting_dots():
        while True:
            print(".", end="", flush=True)
            time.sleep(1)

    registered = False
    first_request = True

    def print_waiting_menu():
        print("\n\nOptions while waiting:")
        print("r - Reconfigure Identity")
        print("a - Reconfigure All (IP and Identity)")
        print("q - Quit")
        print("\nPress any other key to check registration status...")

    while not registered:
        registered, auth_token = request_registration(ip_address, config['sorter_id'])
        
        if registered:
            print("\n✅ Device registration confirmed!")
            break
        elif first_request:
            print("\n⏳ Waiting for admin approval in the GoSort web interface")
            print(f"    Device Identity: {config['sorter_id']}")
            print("    Please approve this device in the web interface...")
            print_waiting_menu()
            first_request = False
        
        # Check for keyboard input (non-blocking)
        if msvcrt.kbhit():
            key = msvcrt.getch().decode().lower()
            if key == 'r':
                print("\nReconfiguring Sorter Identity")
                sorter_id = input("Enter new Sorter Identity (e.g., Sorter1): ")
                config['sorter_id'] = sorter_id
                save_config(config)
                print("\n⏳ Trying with new identity:", config['sorter_id'])
                first_request = True  # Reset to show the waiting message again
                continue
            elif key == 'a':
                print("\n⚙️ Reconfiguring All Settings...")
                # Clear IP and identity
                config['ip_address'] = None
                config['sorter_id'] = None
                save_config(config)
                restart_program()
            elif key == 'q':
                print("\n❌ Registration cancelled. Exiting...")
                return
            else:
                print("\nChecking registration status...", end="", flush=True)
        
        time.sleep(2)  # Check every 2 seconds
        if not first_request:
            print(".", end="", flush=True)

    # Start heartbeat thread
    def heartbeat_loop():
        nonlocal auth_token
        device_identity = config['sorter_id']
        while True:
            if not send_heartbeat(ip_address, auth_token, device_identity):
                # Request registration again if heartbeat fails
                registered, new_token = request_registration(ip_address, device_identity)
                if registered:
                    auth_token = new_token
                else:
                    print("\n❌ Device registration lost or waiting for approval")
                    print("   Please check the web interface...")
                    time.sleep(5)  # Wait before retrying
            time.sleep(1)
    
    heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    heartbeat_thread.start()
    
    mega_ports = list_arduino_ports()
    
    if not mega_ports:
        print("No Arduino Mega found. Please check connection.")
        return
    
    if len(mega_ports) > 1:
        print("\nMultiple Arduino ports found. Choose:")
        for i, port in enumerate(mega_ports):
            print(f"{i+1}. {port}")
        choice = int(input("Enter the number of your choice: ")) - 1
        port = mega_ports[choice]
    else:
        port = mega_ports[0]
    
    ser = connect_to_arduino(port)
    if not ser:
        return
    
    ser.write('gosort_ready\n'.encode())
    time.sleep(0.1)
    
    while ser.in_waiting:
        response = ser.readline().decode().strip()
        if response:
            print(f"🟢 Arduino Response: {response}")
    
    print("\n✅ Connected to Arduino Mega 2560")
    
    maintenance_active = False

    def print_menu():
        if not maintenance_active and not is_maintenance_mode():
            print("\nTrash Selection Menu:")
            print("1. Non Bio")
            print("2. Bio")
            print("3. Recyclable")
            print("r. Reconfigure IP")
            print("i. Reconfigure Identity")
            print("c. Clear All Configuration")
            print("q. Quit")

    print_menu()

    while True:
        # Check for maintenance commands first
        maintenance_command = check_maintenance_command()
        if maintenance_command:
            if maintenance_command == 'maintenance_start':
                print("\n🔧 Entering maintenance mode...")
                maintenance_active = True
                ser.write("maintmode\n".encode())
                time.sleep(0.1)
                while ser.in_waiting:
                    response = ser.readline().decode().strip()
                    if response:
                        print(f"🟢 Arduino Response: {response}")
                continue
            elif maintenance_command == 'maintenance_end':
                print("\n✅ Exiting maintenance mode...")
                maintenance_active = False
                ser.write("maintend\n".encode())
                time.sleep(0.1)
                while ser.in_waiting:
                    response = ser.readline().decode().strip()
                    if response:
                        print(f"🟢 Arduino Response: {response}")
                print_menu()
                continue
            elif maintenance_command == 'maintenance_keep':
                # Just a keepalive signal, no action needed
                continue
            elif maintenance_command in ['bio', 'nbio', 'recyc', 'sweep1', 'sweep2', 'unclog'] and (maintenance_active or is_maintenance_mode()):
                print(f"\n🔧 Maintenance: Executing {maintenance_command}...")
                ser.write(f"{maintenance_command}\n".encode())
                time.sleep(0.1)
                while ser.in_waiting:
                    response = ser.readline().decode().strip()
                    if response:
                        print(f"🟢 Arduino (Maintenance): {response}")
                continue

        # If in maintenance mode, skip normal operation
        if maintenance_active or is_maintenance_mode():
            time.sleep(0.1)  # Short sleep to prevent CPU hogging
            continue

        # Non-blocking input check using msvcrt
        if msvcrt.kbhit():
            key = msvcrt.getch().decode()
        
        # Check for maintenance commands first
        maintenance_command = check_maintenance_command()
        if maintenance_command:
            if maintenance_command == 'maintenance_start':
                print("\n🔧 Entering maintenance mode...")
                maintenance_active = True
                ser.write("maintmode\n".encode())
                time.sleep(0.1)
                while ser.in_waiting:
                    response = ser.readline().decode().strip()
                    if response:
                        print(f"🟢 Arduino Response: {response}")
                continue
            elif maintenance_command == 'maintenance_end':
                print("\n✅ Exiting maintenance mode...")
                maintenance_active = False
                ser.write("maintend\n".encode())
                time.sleep(0.1)
                while ser.in_waiting:
                    response = ser.readline().decode().strip()
                    if response:
                        print(f"🟢 Arduino Response: {response}")
                print_menu()
                continue
            elif maintenance_command == 'maintenance_keep':
                # Just a keepalive signal, no action needed
                continue
            elif maintenance_command in ['bio', 'nbio', 'recyc', 'sweep1', 'sweep2', 'unclog'] and (maintenance_active or is_maintenance_mode()):
                print(f"\n🔧 Maintenance: Executing {maintenance_command}...")
                ser.write(f"{maintenance_command}\n".encode())
                time.sleep(0.1)
                while ser.in_waiting:
                    response = ser.readline().decode().strip()
                    if response:
                        print(f"🟢 Arduino (Maintenance): {response}")
                continue

        # If in maintenance mode, skip normal operation
        if maintenance_active or is_maintenance_mode():
            time.sleep(0.1)  # Short sleep to prevent CPU hogging
            continue

        # Process normal operation input only if available and not in maintenance mode
        if msvcrt.kbhit():
            choice = msvcrt.getch().decode().lower()
            
            if choice == 'q':
                # Set device as offline before quitting
                try:
                    url = f"http://{ip_address}/GoSort_Web/gs_DB/set_device_offline.php"
                    requests.post(url, json={
                        'token': auth_token,
                        'identity': config['sorter_id']
                    })
                except:
                    pass  # Don't prevent shutdown if request fails
                break
            elif choice == 'r':
                # Set device as offline before resetting
                try:
                    url = f"http://{ip_address}/GoSort_Web/gs_DB/set_device_offline.php"
                    requests.post(url, json={
                        'token': auth_token,
                        'identity': config['sorter_id']
                    })
                except:
                    pass
                config = load_config()
                config['ip_address'] = None
                save_config(config)
                print("\nIP configuration reset. Please restart the application.")
                break
            elif choice == 'i':
                # Set device as offline before reconfiguring
                try:
                    url = f"http://{ip_address}/GoSort_Web/gs_DB/set_device_offline.php"
                    requests.post(url, json={
                        'token': auth_token,
                        'identity': config['sorter_id']
                    })
                except:
                    pass
                config = load_config()
                print("\nReconfiguring Sorter Identity")
                sorter_id = input("Enter new Sorter Identity (e.g., Sorter1): ")
                config['sorter_id'] = sorter_id
                save_config(config)
                print("\nSorter Identity updated. Restarting...")
                restart_program()
            elif choice == 'c':
                # Set device as offline before clearing config
                try:
                    url = f"http://{ip_address}/GoSort_Web/gs_DB/set_device_offline.php"
                    requests.post(url, json={
                        'token': auth_token,
                        'identity': config['sorter_id']
                    })
                except:
                    pass
                # Clear all configuration
                print("\n⚠️ Clearing all configuration...")
                if os.path.exists('gosort_config.json'):
                    os.remove('gosort_config.json')
                if os.path.exists('python_auth_token.txt'):
                    os.remove('python_auth_token.txt')
                print("✅ All configuration cleared. Please restart the application.")
                break
            elif choice in ['1', '2', '3']:
                command = {
                    '1': 'nbio',
                    '2': 'bio',
                    '3': 'recyc'
                }[choice]
                ser.write(f"{command}\n".encode())
                print(f"\n🔄 Moving to {command.upper()}...")
                time.sleep(0.1)
                while ser.in_waiting:
                    response = ser.readline().decode().strip()
                    if response:
                        print(f"🟢 Arduino Response: {response}")
                print_menu()
            elif choice not in ['\r', '\n']:  # Ignore enter key presses
                print("\nInvalid choice. Please choose 1, 2, 3, r for IP config, i for Identity config, or q to quit")
        

    
    ser.close()
    print("🔌 Connection closed")

if __name__ == "__main__":
    main()
