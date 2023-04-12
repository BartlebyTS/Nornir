import requests
import yaml
from environs import Env
from hardware_dictionary import hardware_dict
#define match for various hardware types to how you want them matched together in seperate file (mine is very large).


# Declare env

env = Env()
env.read_env()
LIBRE_API_KEY = env('API_KEY')
WEB_ADDRESS = env('LIBRENMS_ADDRESS')

# Pull info from LibreNMS

headers = { "X-Auth-Token": LIBRE_API_KEY }
url = f"https://{WEB_ADDRESS}/api/v0/devices"

res = requests.get(url, headers=headers, verify=False).json()

devices = res['devices']

hardware_list = {}

# Write hosts.yaml for Nornir

def write_yaml_to_file(py_obj,filename):
    with open(f'{filename}.yaml', 'w',) as f :
        yaml.dump(py_obj,f,sort_keys=False) 
    print('Written to file successfully')


dict1 = {}
for i in devices:
    try:
        sysname = i['sysName']
        hostname = i['hostname']
        pregroups = i['hardware']
        device_id = i['device_id']
        groups = hardware_dict[pregroups]
        dict1.update({sysname: {'hostname':hostname, 'groups':[groups], 'data':{'device_id':device_id}}})
    except:
        print(hostname, "didn't work")
write_yaml_to_file(dict1, 'test')





