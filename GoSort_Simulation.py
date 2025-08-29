import time
import requests
import json
import os
import socket
import concurrent.futures
import threading
import msvcrt
import sys

class SimulatedArduino:
    def __init__(self):
        self.current_position = 'center'  # Start at center
        self.moving = False
        self.last_command = None
    
    def write(self, command):
        command = command.decode('utf-8').strip()
        self.last_command = command
        self.moving = True
        print(f"\n🔄 Simulated servo moving to {command}...")
        time.sleep(2)  # Simulate movement time
        self.current_position = command
        self.moving = False
        print(f"✅ Simulated servo moved to {command}")
        return len(command)
    
    def readline(self):
        if self.moving:
            return b"moving\n"
        return b"ready\n"
    
    def is_open(self):
        return True

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
        print("\r❌ Server check failed - Invalid response")
        return False
    except requests.exceptions.RequestException as e:
        print(f"\r❌ Server check failed - {str(e)}")
        return False

def check_maintenance_commands(ip_address, device_identity, ser):
    try:
        url = f"http://{ip_address}/GoSort_Web/gs_DB/check_maintenance_commands.php"
        response = requests.post(
            url,
            json={'device_identity': device_identity},
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success') and data.get('commands'):
                for cmd in data.get('commands', []):
                    print(f"\n⚙️ Executing maintenance command: {cmd}")
                    ser.write(cmd.encode())
                    time.sleep(0.1)  # Small delay between commands
                    
                # Mark commands as executed
                requests.post(
                    f"http://{ip_address}/GoSort_Web/gs_DB/mark_command_executed.php",
                    json={'device_identity': device_identity},
                    headers={'Content-Type': 'application/json'}
                )
    except Exception as e:
        print(f"\n❌ Error checking maintenance commands: {e}")

def set_device_offline(ip_address, device_identity):
    try:
        url = f"http://{ip_address}/GoSort_Web/gs_DB/set_device_offline.php"
        requests.post(
            url,
            json={'device_identity': device_identity},
            headers={'Content-Type': 'application/json'}
        )
    except:
        pass

def update_connection_status(ip_address, device_identity):
    try:
        url = f"http://{ip_address}/GoSort_Web/gs_DB/connection_status.php"
        requests.post(
            url,
            json={'device_identity': device_identity},
            headers={'Content-Type': 'application/json'}
        )
    except:
        pass

def main():
    print("📦 GoSort Simulation System")
    print("======================")
    
    config = load_config()
    ip_address = config.get('ip_address')
    device_identity = config.get('sorter_id')

    if not ip_address or not device_identity:
        print("\n⚙️ Initial setup required")
        gosort_ips, _ = scan_network()
        
        if not gosort_ips:
            print("\n❌ No GoSort servers found on the network")
            return
        
        print("\nAvailable GoSort servers:")
        for i, ip in enumerate(gosort_ips, 1):
            print(f"{i}. {ip}")
        
        while True:
            try:
                choice = int(input("\nSelect server number: "))
                if 1 <= choice <= len(gosort_ips):
                    ip_address = gosort_ips[choice - 1]
                    break
                print("Invalid selection")
            except ValueError:
                print("Please enter a number")
        
        if not check_server(ip_address):
            return
        
        device_identity = input("\nEnter sorter ID (e.g., SORTER001): ").strip()
        if not device_identity:
            print("\n❌ Invalid sorter ID")
            return
        
        config = {'ip_address': ip_address, 'sorter_id': device_identity}
        save_config(config)
        print("\n✅ Configuration saved")
    
    print(f"\nServer IP: {ip_address}")
    print(f"Sorter ID: {device_identity}")
    
    # Create simulated Arduino
    ser = SimulatedArduino()
    print("\n✅ Simulated hardware initialized")
    
    try:
        while True:
            update_connection_status(ip_address, device_identity)
            
            # Check for maintenance mode and commands
            if check_maintenance_mode(ip_address, device_identity):
                print("\r🔧 Device in maintenance mode - Checking for commands...", end="", flush=True)
                check_maintenance_commands(ip_address, device_identity, ser)
                time.sleep(1)
                continue
            
            response = ser.readline()
            if response == b"ready\n":
                print("\r✅ System ready - Listening for commands", end="", flush=True)
            
            # Show options menu
            print("\r⌨️  Options: [1]Bio [2]Non-Bio [3]Hazardous [4]Mixed [5]Test Mode [6]Menu [7]Setup [q]Quit", end="", flush=True)
            
            # Check for keyboard input
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b'1':
                    print("\n🟢 Moving to Bio position")
                    ser.write(b"zdeg")
                elif key == b'2':
                    print("\n🔵 Moving to Non-Bio position")
                    ser.write(b"ndeg")
                elif key == b'3':
                    print("\n🟡 Moving to Hazardous position")
                    ser.write(b"odeg")
                elif key == b'4':
                    print("\n⚫ Moving to Mixed position")
                    ser.write(b"tdeg")
                elif key == b'5':
                    print("\n🔧 Test Mode")
                    print("1. Pan Sweep Test")
                    print("2. Full Sweep Test")
                    print("3. Back")
                    while True:
                        if msvcrt.kbhit():
                            test_key = msvcrt.getch()
                            if test_key == b'1':
                                print("\n🔄 Running Pan Sweep Test")
                                ser.write(b"sweep1")
                                break
                            elif test_key == b'2':
                                print("\n🔄 Running Full Sweep Test")
                                ser.write(b"sweep2")
                                break
                            elif test_key == b'3':
                                break
                elif key == b'6':
                    print("\n📋 Menu")
                    print("1. Bio")
                    print("2. Non-Bio")
                    print("3. Hazardous")
                    print("4. Mixed")
                    print("5. Test Mode")
                    print("6. This Menu")
                    print("7. Setup")
                    print("q. Exit")
                elif key == b'7':
                    print("\n⚙️ Setup")
                    gosort_ips, _ = scan_network()
                    
                    if not gosort_ips:
                        print("\n❌ No GoSort servers found on the network")
                        continue
                    
                    print("\nAvailable GoSort servers:")
                    for i, ip in enumerate(gosort_ips, 1):
                        print(f"{i}. {ip}")
                    
                    while True:
                        try:
                            choice = int(input("\nSelect server number (or 0 to cancel): "))
                            if choice == 0:
                                break
                            if 1 <= choice <= len(gosort_ips):
                                ip_address = gosort_ips[choice - 1]
                                if not check_server(ip_address):
                                    break
                                
                                device_identity = input("\nEnter sorter ID (e.g., SORTER001, or Enter to cancel): ").strip()
                                if not device_identity:
                                    break
                                
                                config = {'ip_address': ip_address, 'sorter_id': device_identity}
                                save_config(config)
                                print("\n✅ Configuration saved")
                                break
                            print("Invalid selection")
                        except ValueError:
                            print("Please enter a number")
                    print("\nReturning to main menu...")
                elif key == b'q':
                    print("\n👋 Exiting...")
                    break
            
            time.sleep(0.1)
    
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down...")
    finally:
        set_device_offline(ip_address, device_identity)

if __name__ == "__main__":
    main()
