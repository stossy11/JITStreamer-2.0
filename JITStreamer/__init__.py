import atexit
import asyncio
import click
import socket
import logging
import json
import multiprocessing
import configparser
import requests
import os
import concurrent.futures
from flask import Flask, request, jsonify, redirect, url_for
from urllib.parse import urlparse
from time import sleep
from zeroconf import ServiceInfo, Zeroconf
from werkzeug.utils import secure_filename

from pymobiledevice3 import usbmux, pair_records, common
from pymobiledevice3.remote.common import TunnelProtocol
from pymobiledevice3.exceptions import AlreadyMountedError
from pymobiledevice3.usbmux import select_devices_by_connection_type
from pymobiledevice3.lockdown import create_using_tcp, LockdownClient, create_using_usbmux
from pymobiledevice3.services.installation_proxy import InstallationProxyService
from pymobiledevice3.services.mobile_image_mounter import auto_mount_personalized
from pymobiledevice3.services.dvt.instruments.process_control import ProcessControl
from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
from pymobiledevice3.tunneld import get_tunneld_devices, TUNNELD_DEFAULT_ADDRESS, TunneldRunner

from pymobiledevice3._version import __version__ as pymd_ver


app = Flask("JITStreamer")
logging.basicConfig(level=logging.WARNING)

config_folder = os.path.join(os.path.expanduser('~'), '.JITStreamer')
config_path = os.path.join(config_folder, 'config.ini')

# Ensure the .JITStreamer directory exists
if not os.path.exists(config_folder):
    os.makedirs(config_folder)
    
# Initialize and read the config file
config = configparser.ConfigParser(allow_no_value=True)
config.read(config_path)

# If needed, set default values for your configuration
if not config.has_section('Settings'):
    config.add_section('Settings')
    config.set('Settings', 'see_udid', 'false')
    config.set('Settings', 'refresh_all', 'false')
    config.set('Settings', 'port', '8080')
    

if not config.has_section('Tunnel'):
    config.add_section('Tunnel')
    config.set('Tunnel', 'start-tunneld', 'true')
    config.set('Tunnel', 'mobdev2', 'true')
    config.set('Tunnel', 'usb', 'true')
    config.set('Tunnel', 'wifi', 'true')
    config.set('Tunnel', 'usbmuxd', 'true')
    config.set('Tunnel', 'start-tunnel-on-every-rq', 'true')

# Save the default configuration back to the file if it's newly created
with open(config_path, 'w') as configfile:
    config.write(configfile)

DEVS_FILE = os.path.join(config_folder, 'devices.json')

devs = []

class App:
    __slots__ = ('name', 'bundle', 'pid')

    def __init__(self, name: str, bundle: str, pid: int = -1):
        self.name = name
        self.bundle = bundle
        self.pid = pid

    def __repr__(self):
        return f"App<'{self.name}', {self.pid}>"

    def asdict(self):
        return {"name": self.name, "bundle": self.bundle, "pid": self.pid}

class Device:
    __slots__ = ('handle', 'name', 'udid', 'apps')

    def __init__(self, handle, name: str, udid: str, apps: list[App]):
        self.handle = handle
        self.name = name
        self.udid = udid
        self.apps = apps

    def __repr__(self):
        return f"Device<'{self.udid}', {self.apps}>"

    def refresh_apps(self) -> "Device":
        apps = InstallationProxyService(lockdown=self.handle).get_apps()
        apps = {apps[app]['CFBundleDisplayName']: app for app in apps if 'Entitlements' in apps[app]
                and 'get-task-allow' in apps[app]['Entitlements'] and apps[app]['Entitlements']['get-task-allow']}
        self.apps = [App(name, bundle) for name, bundle in apps.items()]
        save_devs()
        return self

    def launch_app(self, bundle_id: str, sus: bool = False) -> int:
        with DvtSecureSocketProxyService(lockdown=self.handle) as dvt:
            process_control = ProcessControl(dvt)
            return process_control.launch(bundle_id=bundle_id, arguments={},
                                          kill_existing=False, start_suspended=sus,
                                          environment={})

    def enable_jit(self, name: str):
        apps = [a for a in self.apps if a.name == name or a.bundle == name]
        if len(apps) == 0:
            return f"Could not find {name!r}!"
        app = apps[0]

        if app.pid > 0 and app.pid == self.launch_app(app.bundle):
            return f"JIT already enabled for {name!r}!"

        debugserver = \
        (host, port) = \
        self.handle.service.address[0], self.handle.get_service_port('com.apple.internal.dt.remote.debugproxy')

        app.pid = self.launch_app(app.bundle, True)

        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        logging.info(f"Connecting to [{host}]:{port}")
        s.connect(debugserver)

        s.sendall(b'$QStartNoAckMode#b0')
        logging.info(f"StartNoAckMode: {s.recv(4).decode()}")

        s.sendall(b'$QSetDetachOnError:1#f8')
        logging.info(f"SetDetachOnError: {s.recv(8).decode()}")

        logging.info(f"Attaching to process {app.pid}..")
        s.sendall(f'$vAttach;{app.pid:x}#38'.encode())
        out = s.recv(16).decode()
        logging.info(f"Attach: {out}")

        if out.startswith('$T11thread') or '+' in out:
            s.sendall(b'$D#44')
            new = s.recv(16)
            if any(x in new for x in (b'$T11thread', b'$OK#00', b'+')):
                logging.info("Process continued and detached!")
                logging.info(f"JIT enabled for process {app.pid} at [{host}]:{port}!")
            else:
                logging.info(f"Failed to detach process {app.pid}")
        else:
            logging.info(f"Failed to attach process {app.pid}")

        s.close()
        save_devs()
        return f"Enabled JIT for {app.name!r}!"

    def asdict(self):
        return {self.name: [a.asdict() for a in self.apps]}

def save_devs():
    global devs
    with open(DEVS_FILE, 'w') as f:
        json.dump([d.asdict() for d in devs], f, indent=4)

def load_devs():
    global devs
    try:
        with open(DEVS_FILE, 'r') as f:
            devs_data = json.load(f)
            devs = [Device(None, d['name'], d['udid'], [App(a['name'], a['bundle'], a['pid']) for a in d['apps']]) for d in devs_data]
    except FileNotFoundError:
        devs = []

def mount_device(dev):
    if dev is None:
        logging.warning("Received None device to mount.")
        return None
    
    try:
        # Attempt to mount the device
        asyncio.run(auto_mount_personalized(dev))
        return dev
    except AlreadyMountedError:
        logging.info(f"Device {dev} already mounted.")
        return dev
    except Exception as e:
        logging.error(f"Error mounting device {dev}: {e}")
        return None

def refresh_devs():
    global devs
    with app.app_context():
        # Use ThreadPoolExecutor to queue auto_mount_personalized with 2-3 workers
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = []
            tunneld_devices = get_tunneld_devices()
            
            if not tunneld_devices:
                logging.warning("No devices returned from get_tunneld_devices().")
                return  # Early exit if no devices
            
            for dev in tunneld_devices:
                if dev is not None:
                    # Submit each mounting task to the executor
                    futures.append(executor.submit(mount_device, dev))
                else:
                    logging.warning("Received None device from get_tunneld_devices().")
            
            # Process the results as they complete
            for future in concurrent.futures.as_completed(futures):
                dev = future.result()  # Get the device after it's mounted
                if dev is not None:
                    try:
                        # Check if device already exists in the list
                        db_device = next((d for d in devs if d.udid == dev.udid), None)
                        
                        if not db_device:
                            # Add new device
                            new_device = Device(dev, dev.name, dev.udid, [])
                            new_device.refresh_apps()
                            devs.append(new_device)
                    except Exception as e:
                        logging.error(f"Error while processing device {dev}: {e}")
                else:
                    logging.warning("Received None result from a future.")
    
    save_devs()

def get_device(udid: str):
    global devs
    d = [d for d in devs if d.udid == udid]
    return None if len(d) != 1 else d[0]

def settings(key):
    return config.get('Settings', key)

def tunnelsettings(key):
    return config.getboolean('Tunnel', key)

@app.route('/', methods=['GET'])
def list_devices():
    # Query the database to get all devices
    devices = devs

    # Check the see_udid setting and decide how to format the response
    if settings('see_udid'):
        response = {device.name: device.udid for device in devices} if devices else {"ERROR": "Could not find any device!"}
    else:
        return jsonify({"ERROR": "This Request is not Permitted!"})
        
    return jsonify(response)

@app.route('/ver', methods=['GET'])
def version():
    return jsonify({"pymobiledevice3": pymd_ver, "SideJITServer": "2.0 Beta"})

@app.route('/re', methods=['GET'])
def refresh():
    # refresh_all
    if settings('refresh_all'):
        refresh_devs()
        return jsonify({"OK": "Refreshed!"})
        
    return jsonify({"ERROR": "This Request is not Permitted!"})


@app.route('/<device_id>/', methods=['GET'])
def get_device_apps(device_id):
    ip = request.remote_addr
    udid = device_id
    start_tunneld_ip(ip, udid)
    device = get_device(device_id)
    if device:
        return jsonify([a.asdict() for a in device.apps])
    return jsonify({"ERROR": "Device not found!"}), 404

@app.route('/add', methods=['GET'])
def add_device():
    ip = request.args.get('ip')
    udid = request.args.get('udid')
    if not ip or not udid:
        return jsonify({"ERROR": "Missing 'ip' or 'udid' parameter"}), 400
        
    try:
        start_tunneld_ip(ip, udid)
        return jsonify({"OK": response.text})
    except Exception as e:
        return jsonify({"ERROR": str(e)}), 500

@app.route('/<device_id>/re/', methods=['GET'])
def refresh_device_apps(device_id):
    device = get_device(device_id)
    if device:
        device.refresh_apps()
        return jsonify({"OK": "Refreshed app list!"})
    return jsonify({"ERROR": "Device not found!"}), 404

@app.route('/<device_id>/<action>/', methods=['GET'])
def perform_action(device_id, action):
    device = get_device(device_id)
    ip = request.remote_addr
    udid = device_id
    start_tunneld_ip(ip, device_id)
    if device:
        result = device.enable_jit(action)
        return jsonify(result)
    else:
        ip = request.remote_addr
        udid = device_id
        start_tunneld_ip(ip, udid)
        device = get_device(device_id)
        if device:
            result = device.enable_jit(action)
            return jsonify(result)
        return jsonify({"ERROR": "Device not found!"}), 404
            
    

def start_tunneld_proc():
    TunneldRunner.create("0.0.0.0", TUNNELD_DEFAULT_ADDRESS[1],
                         protocol=TunnelProtocol('quic'), mobdev2_monitor=tunnelsettings("mobdev2"), usb_monitor=tunnelsettings("usb"), wifi_monitor=tunnelsettings("wifi"), usbmux_monitor=tunnelsettings("usbmuxd"))
                         
@app.route('/uploads/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        # Check if the post request has the file part
        if 'file' not in request.files:
            return jsonify({"ERROR": "No file part"}), 400
        file = request.files['file']
        
        # If the user does not select a file, the browser also
        # submits an empty part without filename
        if file.filename == '':
            return jsonify({"ERROR": "No selected file"}), 400
        
        if file:
            filename = secure_filename(file.filename)
            
            # Define the path to the ~/.pymobiledevice3/ directory
            user_home = os.path.expanduser('~')
            upload_folder = os.path.join(user_home, '.pymobiledevice3')
            
            if not filename.lower().endswith('.plist'):
                return jsonify({"ERROR": "Only .plist files are allowed"}), 400

            # Create the directory if it doesn't exist
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            # Save the file to the specified directory
            file_path = os.path.join(upload_folder, filename)
            try:
                file.save(file_path)
            except:
                return jsonify({"OK": f"File upload failed"}), 400
            
            file_root, file_extension = os.path.splitext(filename)
        
            ip = request.remote_addr
            start_tunneld_ip(ip, file_root)
            return jsonify({"OK": f"File uploaded"}), 200
    
    return '''
    <!doctype html>
    <title>Upload new File</title>
    <h1>Upload new File</h1>
    <form method=post enctype=multipart/form-data>
      <input type=file name=file>
      <input type=submit value=Upload>
    </form>
    '''

def start_tunneld_ip(ip, udid):
    tunnel_url = f"http://127.0.0.1:{TUNNELD_DEFAULT_ADDRESS[1]}/start-tunnel?ip={ip}&udid={udid}"
    try:
        response = requests.get(tunnel_url)
        refresh_devs()
    except:
        print('Unable to add tunnel')

def prompt_device_list(device_list: list):
    device_question = [inquirer3.List('device', message='choose device', choices=device_list, carousel=True)]
    try:
        result = inquirer3.prompt(device_question, raise_keyboard_interrupt=True)
        return result['device']
    except KeyboardInterrupt:
        raise Exception()

@click.command()
@click.option('-e', '--version', is_flag=True, default=False, help='Prints the versions of pymobiledevice3 and JITStreamer')
@click.option('-t', '--timeout', default=5, help='The number of seconds to wait for the pymd3 admin tunnel')
@click.option('-v', '--verbose', default=0, count=True, help='Increase verbosity (-v for INFO, -vv for DEBUG)')
@click.option('-y', '--pair', is_flag=True, default=False, help='Alternate pairing mode, will wait to pair to 1 device')
def start_server(verbose, timeout, pair, version):
    if version:
        click.echo(f"pymobiledevice3: {pymd_ver}" + "\n" + f"SideJITServer: 2.0 Beta")
        return

    if pair:
        click.echo("Attempting to pair to a device! (Ctrl+C to stop)")
        devices = select_devices_by_connection_type(connection_type='USB')
        while len(devices) == 0:
            devices = select_devices_by_connection_type(connection_type='USB')
            click.echo("No devices..")
            sleep(3)

        create_using_usbmux()
        devices = [create_using_usbmux(serial=device.serial, autopair=False) for device in devices]
        print(devices)
        if len(devices) > 1:
            dev = prompt_device_list(devices)
        else:
            dev = devices[0]
        dev.pair()
        if "y" not in input("Continue? [y/N]: ").lower():
            return

    log_levels = [logging.WARNING, logging.INFO, logging.DEBUG]
    verbosity_level = min(len(log_levels) - 1, verbose)
    logging.getLogger().setLevel(log_levels[verbosity_level])

    if tunnelsettings("start-tunneld"):
        tunneld = multiprocessing.Process(target=start_tunneld_proc)
        tunneld.start()
        sleep(timeout)
        refresh_devs()
        
    try:
        # Try to convert to integer
        port = int(settings('port'))
    except:
        # If conversion fails, check if it's a boolean
        port = 8080
    
    app.run(host='0.0.0.0', port=port)
