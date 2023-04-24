from nornir_librenms.nr_config import init_nornir
from environs import Env


# Declare ENV variables

env = Env()
env.read_env()
USER = env('LIBRE_USERNAME')
PASSWORD = env('LIBRE_PASSWORD')
LIBRE_API_KEY = env('API_KEY')
WEB_ADDRESS = env('LIBRENMS_ADDRESS')

nr = init_nornir(
    username=USER,
    password=PASSWORD,
    url=f'http://{WEB_ADDRESS}/api/v0/devices/',
    api_key=LIBRE_API_KEY
)

print(nr.inventory.hosts)
