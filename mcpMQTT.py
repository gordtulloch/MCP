#!/usr/bin/env python3

# From code by aaronwmorris thanks!
import sys
from pathlib import Path
from pprint import pformat  # noqa: F401
import json
import paho.mqtt.publish as publish
import logging

from mcpConfig import McpConfig

from sqlalchemy.orm.exc import NoResultFound

sys.path.append(str(Path(__file__).parent.absolute().parent))

logger = logging.getLogger('oMCP')

class McpMQTT(object):
    discovery_base_topic = 'homeassistant'
    unique_id_base = '001'
    
    # maps to SensorDeviceClass
    HA_SENSOR_DEVICE_CLASS = {
        SENSOR_TEMPERATURE          : 'TEMPERATURE',
    }


    # https://github.com/home-assistant/core/blob/master/homeassistant/const.py
    HA_UNIT_MAP = {
        SENSOR_TEMPERATURE : {
            'c' : '°C',
            'f' : '°F',
            'k' : 'K',
            'degree'  : '°',
            'degrees' : '°',
        },
    }

    def __init__(self):
        self.config = McpConfig()

    def main(self, retain=True):
        if not self.config.get('MQTTENABLE'):
            logger.error('MQ Publishing not enabled')
            sys.exit(1)

        basic_sensor_list = [
            {
                'component' : 'image',
                'object_id' : 'indi_allsky_latest',
                'config' : {
                    'name' : "indi-allsky Camera",
                    'unique_id' : 'indi_allsky_latest_{0}'.format(self.unique_id_base),
                    'content_type' : 'image/jpeg',
                    #'content_type' : 'image/png',
                    'image_topic' : '/'.join((base_topic, 'latest')),
                },
            },
            {
                'component' : 'sensor',
                'object_id' : 'indi_allsky_exposure',
                'config' : {
                    'name' : 'Exposure',
                    'unit_of_measurement' : 's',
                    'unique_id' : 'indi_allsky_exposure_{0}'.format(self.unique_id_base),
                    'state_topic' : '/'.join((base_topic, 'exposure')),
                },
            },
        ]

        extended_sensor_list = [
            {
                'component' : 'sensor',
                'object_id' : 'indi_allsky_cpu_total',
                'config' : {
                    'name' : 'CPU Total',
                    'unique_id' : 'indi_allsky_cpu_total_{0}'.format(self.unique_id_base),
                    'state_topic' : '/'.join((base_topic, 'cpu', 'total')),
                },
            },
            {
                'component' : 'sensor',
                'object_id' : 'indi_allsky_memory_total',
                'config' : {
                    'name' : 'Memory Total',
                    'unit_of_measurement' : '%',
                    'unique_id' : 'indi_allsky_memory_total_{0}'.format(self.unique_id_base),
                    'state_topic' : '/'.join((base_topic, 'memory', 'total')),
                },
            },
        ]


        extended_sensor_list.append({
                    'component' : 'sensor',
                    'object_id' : 'indi_allsky_thermal_{0}_{1}'.format(t_key_safe, label_safe),
                    'config' : {
                        'name' : 'Thermal {0} {1}'.format(t_key, label),
                        'unit_of_measurement' : '°',
                        'unique_id' : 'indi_allsky_thermal_{0}_{1}_{2}'.format(t_key_safe, label_safe, self.unique_id_base),
                        'state_topic' : '/'.join((base_topic, 'temp', t_key_safe, label_safe)),
                    },
                })

        message_list = list()
        for sensor in basic_sensor_list:
            message = {
                'topic'    : '/'.join((self.discovery_base_topic, sensor['component'], sensor['object_id'], 'config')),
                'payload'  : json.dumps(sensor['config']),
                'qos'      : 0,
                'retain'   : retain,
            }
            message_list.append(message)

            logger.warning('Create topic: %s', message['topic'])
            #logger.warning('Data: %s', pformat(message))


        for sensor in extended_sensor_list:
            message = {
                'topic'    : '/'.join((self.discovery_base_topic, sensor['component'], sensor['object_id'], 'config')),
                'payload'  : json.dumps(sensor['config']),
                'qos'      : 0,
                'retain'   : retain,
            }

            message_list.append(message)

            logger.warning('Create topic: %s', message['topic'])
            logger.warning('Data: %s', pformat(message))


        logger.warning('Messages: %s', pformat(message_list))

        mq_auth = {
                'username' : self.config.get('MQTTUSER'),
                'password' : self.config.get('MQTTPASS'),
            }

        logger.warning('Publishing discovery data')
        publish.multiple(
            message_list,
            transport=transport,
            hostname=hostname,
            port=self._port,
            client_id='',
            keepalive=60,
            auth=mq_auth,
            tls=mq_tls,
        )