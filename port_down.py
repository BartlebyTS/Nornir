# Import modules
from nornir import InitNornir
from environs import Env
import requests
import json
import urllib3
import re
from nornir_utils.plugins.functions import print_result
from netmiko import ConnectHandler
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Declare ENV variables

env = Env()
env.read_env()
LIBRE_API_KEY = env('API_KEY')
WEB_ADDRESS = env('LIBRENMS_ADDRESS')
USER = env('NORNIR_USERNAME')
PASSWORD = env('NORNIR_PASSWORD')

# Initiate Nornir

nr = InitNornir(config_file="config.yaml")
platform_brocade="brocade_fastiron"
platform_cisco_standard="cisco_ios"
platform_cisco_asa="cisco_asa"
target_hosts_brocade = nr.filter(platform=platform_brocade)
target_hosts_cisco_standard = nr.filter(platform=platform_cisco_standard)
target_hosts_cisco_asa = nr.filter(platform=platform_cisco_asa)
device_id_list = []
host_to_id_list_map = {}
for host in target_hosts_brocade.inventory.hosts:
    check = nr.inventory.hosts[host]['device_id']
    device_id_list.append(check)
    host_to_id_list_map[check] = host
for host in target_hosts_cisco_standard.inventory.hosts:
    check = nr.inventory.hosts[host]['device_id']
    device_id_list.append(check)
    host_to_id_list_map[check] = host
for host in target_hosts_cisco_asa.inventory.hosts:
    check = nr.inventory.hosts[host]['device_id']
    device_id_list.append(check)
    host_to_id_list_map[check] = host

print(device_id_list)

# Pull LibreNMS port IDs from Devices in inventory

headers = { "X-Auth-Token": LIBRE_API_KEY }
ports_to_check = {}
for device_id in device_id_list:
    url = (f"https://{WEB_ADDRESS}/api/v0/ports/search/device_id/{device_id}")
    res = requests.get(url, headers=headers, verify=False).json()
    ports = res['ports']
    for i in ports:
        if i['device_id'] == device_id:
            ports_to_check[i['port_id']] = device_id
        else:
            continue

# Check and remove if ports are part of lag, you can bring down ports in a lag if the primary is down and you disable it


bad_ports = {}
duplicate = {}
lag_ports = []
lag_ports_dict = {}
port_id_api_call = {}
for port_id in ports_to_check:
    try:
        url = (f"https://{WEB_ADDRESS}/api/v0/ports/{port_id}")
        res_ports = requests.get(url, headers=headers, verify=False).json()
        port_id_api_call[port_id] = res_ports['port'][0]
    except:
        print(f"{port_id} didn't work")
for port_id in ports_to_check:
    try:
        checking_ports = port_id_api_call[port_id]
        if checking_ports['ifPhysAddress'] not in duplicate:
            duplicate[checking_ports['ifPhysAddress']] = port_id
        else:
            lag_ports_dict[checking_ports['ifPhysAddress']] = duplicate[checking_ports['ifPhysAddress']]
            lag_ports.append(port_id)
    except:
        print(f"{port_id} didn't work")
for i in lag_ports_dict:
     lag_ports.append(lag_ports_dict[i])
for i in lag_ports:
    del ports_to_check[i]

# Check if Ports are Admin UP Link Down and have been for an extended period (not flapping)

for port_id in ports_to_check:
    try:
        checking_ports = port_id_api_call[port_id]
        if (checking_ports['ifLastChange'] > 10000000 or checking_ports['ifLastChange'] == 0) and checking_ports['ifAdminStatus'] == 'up'\
        and checking_ports['ifOperStatus'] == 'down' and checking_ports['device_id'] not in bad_ports:
            bad_ports[checking_ports['device_id']] = [checking_ports['ifDescr']]
        elif (checking_ports['ifLastChange'] > 10000000 or checking_ports['ifLastChange'] == 0) and checking_ports['ifAdminStatus'] == 'up'\
        and checking_ports['ifOperStatus'] == 'down' and checking_ports['device_id'] in bad_ports:
            bad_ports[checking_ports['device_id']].append(checking_ports['ifDescr'])
        else:
            continue
    except:
        print(f"port {port_id} in device {checking_ports['device_id']} did not work")

# Convert the Librenms device ID that was previously used for API calls to hostname

bad_port_hostname = {}
for device in bad_ports:
	device_id_conversion = host_to_id_list_map[device] 
	bad_port_hostname[device_id_conversion] = bad_ports[device]
foundry_devices = {}
brocade_devices = {}
cisco_standard_devices = {}
cisco_asa_devices = {}
# In current iteration just doing old Brocade switching infrastructure and seperating them here

print(bad_port_hostname)

for device in bad_port_hostname:
    group_check = nr.inventory.hosts[f'{device}'].dict()
    print(group_check)
    if group_check['groups'] == ['foundry_networking']:
        foundry_devices[device] = bad_port_hostname[device]
    elif group_check['groups'] == ['brocade_fastiron'] or group_check['groups'] == ['brocade_ironware']:
        brocade_devices[device] = bad_port_hostname[device]
    elif group_check['groups'] == ['cisco_standard']:
        cisco_standard_devices[device] = bad_port_hostname[device]
    elif group_check['groups'] == ['cisco_asa']:
        cisco_asa_devices[device] = bad_port_hostname[device]

new_foundry = {}
new_brocade = {}
new_cisco_standard = {}
new_cisco_asa = {}

# Use regex to take ports descriptions into forms useful for commands

for device in foundry_devices:
    try:
        list_of_device = foundry_devices[device]
        corrected_ports = []
        for k in list_of_device:
            regex = re.findall('\d+', k)[0]
            corrected_ports.append(f"e {regex}")
        new_foundry[device] = corrected_ports
    except:
        print(f"issue with {device}")
for device in brocade_devices:
    try:
        list_of_devices = brocade_devices[device]
        corrected_ports = []
        for k in list_of_devices:
            if k == 'Management':
                corrected_ports.append('management 1')
            else:
                regex1 = re.findall(r'\d{1,2}\/\d{1,2}\/\d{1,2}:?\d?', k)[0]
                corrected_ports.append(f"e {regex1}")
        new_brocade[device] = corrected_ports
    except:
        print(f" {device} had an issue")
for device in cisco_standard_devices:
    try:
        list_of_devices = cisco_standard_devices[device]
        corrected_ports = []
        for k in list_of_devices:
            if k == 'Management':
                corrected_ports.append('management 1')
            elif k[0] == 'V':
                continue
            else:
                regex1 = re.findall(r'\d{1,2}\/\d{1,2}\/\d{1,2}:?\d?', k)[0]
                corrected_ports.append(f"e {regex1}")
        new_cisco_standard[device] = corrected_ports
    except:
        print(f" {device} had an issue")
for device in cisco_asa_devices:
    try:
        list_of_devices = cisco_asa_devices[device]
        corrected_ports = []
        for k in list_of_devices:
            if k == 'Management':
                corrected_ports.append('management 1')
            elif k[0] == 'V':
                continue
            else:
                regex1 = re.findall(r'\d{1,2}\/\d{1,2}:?\d?', k)[0]
                corrected_ports.append(f"e {regex1}")
        new_cisco_asa[device] = corrected_ports
    except:
        print(f" {device} had an issue")


# Create dictionary of device with list of commands to run

new_commands = {}
for device in new_brocade:
    try:
        command_device = nr.inventory.hosts[device].dict()['hostname']
        new_command_device_list = []
        for i in new_brocade[device]:
            new_command_device_list.append(f"interface {i}")
            new_command_device_list.append(f"show interface {i} | include Port")
            new_command_device_list.append("disable")
            new_command_device_list.append("exit")
        new_command_device_list.append("write memory")
        new_commands[command_device] = new_command_device_list
    except:
        print(f"issue with {device}")
for device in new_foundry:
    try:
        command_device = nr.inventory.hosts[device].dict()['hostname']
        new_command_device_list = []
        for i in new_foundry[device]:
            new_command_device_list.append(f"interface {i}")
            new_command_device_list.append(f"show interface {i} | include 300 second input rate")
            new_command_device_list.append(f"show interface {i} | include 300 second output rate")
            new_command_device_list.append("disable")
            new_command_device_list.append("exit")
        new_command_device_list.append("write memory")
        new_commands[command_device] = new_command_device_list
    except:
        print(f"issue with {device}")

for device in new_cisco_standard:
    try:
        command_device = nr.inventory.hosts[device].dict()['hostname']
        new_command_device_list = []
        for i in new_cisco_standard[device]:
            new_command_device_list.append(f"interface {i}")
            new_command_device_list.append("shutdown")
            new_command_device_list.append("exit")
        new_command_device_list.append("write memory")
        new_commands[command_device] = new_command_device_list
    except:
        print(f"issue with {device}")

deviceip_to_type = {}
for device in new_cisco_asa:
    try:
        command_device = nr.inventory.hosts[device].dict()['hostname']
        command_type = nr.inventory.hosts[device].dict()['groups']
        deviceip_to_type[command_device] = command_type 
        new_command_device_list = []
        for i in new_cisco_asa[device]:
            new_command_device_list.append(f"interface {i}")
            new_command_device_list.append("shutdown")
            new_command_device_list.append("exit")
        new_command_device_list.append("write memory")
        new_commands[command_device] = new_command_device_list
    except:
        print(f"issue with {device}")



# Use NetMiko to run commands

device_list = list()

for device_ip in new_commands:
    
    device = {
        "device_type": deviceip_to_type[device_ip],
        "host": device_ip,
        "username": USER,
        "password": PASSWORD, 
    }
    device_list.append(device)

busted_devices = []
for each_device in device_list:
    try:
        connection = ConnectHandler(**each_device)
        connection.enable()
        print(f'Connecting to {each_device["host"]}')
        config_commands = new_commands[each_device["host"]]
        output = connection.send_config_set(config_commands)
        print(output)

        print(f'Closing Connection on {each_device["host"]}')
        connection.disconnect()
    except:
        busted_devices.append(each_device)
        print(f"there was an issue with {each_device}")
print(busted_devices)

