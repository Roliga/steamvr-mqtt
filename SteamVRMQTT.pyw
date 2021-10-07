import os
import sys
import json
import time
import random
import openvr
import paho.mqtt.client as mqtt
import atexit
import platform

vrmqtt_app_key='roliga.steamvrmqtt'

app_dir = os.path.dirname(__file__)
manifest_path = os.path.join(app_dir, 'app.vrmanifest')
config_path = os.path.join(app_dir, 'config.json')

class AssistantMQTT:
    mqtt_client = None
    discovery_prefix = ''
    reconnect_seconds = 10
    client_id = ''

    def __init__(self, address, username, password, client_id, port=1883, discovery_prefix='homeassistant'):
        self.discovery_prefix = discovery_prefix
        self.client_id = client_id

        self.mqtt_client = mqtt.Client('SteamVRMQTT-' + str(random.randint(0, 1000)))
        self.mqtt_client.username_pw_set(username, password)
        self.mqtt_client.on_connect = self.mqtt_on_connect

        self.mqtt_client.connect(address, port)
        self.mqtt_client.loop_start()

    def disconnect(self):
        self.mqtt_client.disconnect()

    def format_topic_base(self, component, unique_id):
        return f'{self.discovery_prefix}/{component}/{unique_id}/'

    def format_unique_id(self, id_suffix):
        return f'{self.client_id}-{id_suffix}'

    def publish_config(self, base_topic, payload):
        self.mqtt_client.publish(base_topic + 'config', json.dumps(payload))

    class AssistantMQTTPublisher:
        mqtt_client = None
        topic = ''

        def __init__(self, mqtt_client, topic):
            self.mqtt_client = mqtt_client
            self.topic = topic

        def publish(self, message):
            self.mqtt_client.publish(self.topic, message)

    def mqtt_on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print('MQTT connected!')
        else:
            print('MQTT conenction failed: ' + rc)
            print('Reconnecting MQTT in ' + self.reconnect_seconds + ' seconds..')
            time.sleep(self.reconnect_seconds)
            print('Reconnecting MQTT..')
            self.mqtt_client.reconnect()

    def make_binary_sensor(self, id_suffix, name, device_class):
        topic_base = self.format_topic_base('binary_sensor', self.format_unique_id(id_suffix))
        topic_publish = topic_base + 'state'

        payload = {
                'name': name,
                'device_class': device_class,
                'state_topic': topic_publish
                }
        self.publish_config(topic_base, payload)

        return self.AssistantMQTTPublisher(self.mqtt_client, topic_publish)

    def make_select(self, id_suffix, name, options):
        topic_base = self.format_topic_base('select', self.format_unique_id(id_suffix))
        topic_publish = topic_base + 'state'

        payload = {
                'name': name,
                'options': options,
                'state_topic': topic_publish,
                'command_topic': topic_base + 'set'
                }
        self.publish_config(topic_base, payload)

        return self.AssistantMQTTPublisher(self.mqtt_client, topic_publish)

def get_app_names():
    app_count = openvr.VRApplications().getApplicationCount()
    app_names = []

    for i in range(0, app_count - 1):
        app_key = openvr.VRApplications().getApplicationKeyByIndex(i)
        app_name = openvr.VRApplications().getApplicationPropertyString(app_key, openvr.VRApplicationProperty_Name_String)

        app_names.append(app_name)

    return app_names

def ha_mqtt_exit():
    ha_ovr_online.publish('OFF')
    ha_mqtt.disconnect()

# Connect OpenVR
try:
    ovr = openvr.init(openvr.VRApplication_Overlay)
    ovr_apps = openvr.VRApplications()
    atexit.register(openvr.shutdown)
except:
    print('Failed to connect to OpenVR, is SteamVR running?')
    exit()
print('OpenVR connected!')

# Write vrmanifest
if(not ovr_apps.isApplicationInstalled(vrmqtt_app_key)):
    vrmanifest = {
        'applications': [{
            'app_key': vrmqtt_app_key,
            'launch_type': 'binary',
            'binary_path_windows': sys.executable,
            'arguments': '"' + __file__ + '"',
            'is_dashboard_overlay': True,
            'strings': {
                'en_us': {
                    'name': 'SteamVRMQTT',
                    'description': 'Push SteamVR information via MQTT to Home Assistant.'
                }
            }
        }]
    }
    with open(manifest_path, 'w') as f:
        print(f'Writing manifest to {manifest_path}')
        json.dump(vrmanifest, f, indent=4)

    print(ovr_apps.addApplicationManifest(manifest_path))
    print(ovr_apps.identifyApplication(0, vrmqtt_app_key))
    #ovr_apps.setApplicationAutoLaunch(vrmqtt_app_key, True)

# Parse config
default_mqtt_address     = ''
default_mqtt_port        = 1883
default_mqtt_username    = ''
default_mqtt_password    = ''
default_interval_seconds = 1

if(os.path.exists(config_path)):
    with open(config_path, 'r') as f:
        print(f'Reading config from {config_path}')
        config_json = json.load(f)
else:
    config_json = {
            'mqtt_address': default_mqtt_address,
            'mqtt_port': default_mqtt_port,
            'mqtt_username': default_mqtt_username,
            'mqtt_password': default_mqtt_password,
            'interval_seconds': default_interval_seconds
        }
    with open(config_path, 'w') as f:
        print(f'Writing default config to {config_path}')
        json.dump(config_json, f, indent=4)
        print('Please add MQTT connection details and start again.')
        exit()

mqtt_address     = config_json.get('mqtt_address',     default_mqtt_address)
mqtt_port        = config_json.get('mqtt_port',        default_mqtt_port)
mqtt_username    = config_json.get('mqtt_username',    default_mqtt_username)
mqtt_password    = config_json.get('mqtt_password',    default_mqtt_password)
interval_seconds = config_json.get('interval_seconds', default_interval_seconds)

# Setup MQTT connection
ha_mqtt = AssistantMQTT(
        address = mqtt_address,
        username = mqtt_username,
        password = mqtt_password,
        port = mqtt_port,
        client_id = platform.node())
atexit.register(ha_mqtt_exit)
ha_ovr_activity = ha_mqtt.make_binary_sensor('ovr_activity', 'VR Headset', 'occupancy')
ha_ovr_application = ha_mqtt.make_select('ovr_application', 'VR Application', get_app_names())
ha_ovr_online = ha_mqtt.make_binary_sensor('ovr_online', 'SteamVR', 'connectivity')
ha_ovr_online.publish('ON')

# Main loop
while True:
    # Activity level
    activity_level = openvr.VRSystem().getTrackedDeviceActivityLevel(0)

    if activity_level == 1:
        ha_ovr_activity.publish('ON')
    else:
        ha_ovr_activity.publish('OFF')

    # Current application
    app_pid = ovr_apps.getCurrentSceneProcessId()
    if(app_pid == 0):
        ha_ovr_application.publish('None')
    else:
        app_key = ovr_apps.getApplicationKeyByProcessId(app_pid)
        app_name = ovr_apps.getApplicationPropertyString(app_key, openvr.VRApplicationProperty_Name_String)

        ha_ovr_application.publish(app_name)

    # poll OpenVR events for set interval
    poll_start_time = time.time()
    event = openvr.VREvent_t()
    while time.time() - poll_start_time < interval_seconds:
        while ovr.pollNextEvent(event):
            if(event.eventType == openvr.VREvent_Quit):
                exit()
        time.sleep(1/10) # poll events at least 10 times per second
