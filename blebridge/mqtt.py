import paho.mqtt.client as client


class MQTTHost:

    def __init__(self, on_connect):
        self._client = client.Client()
        self._client.on_connect = on_connect

    def start(self):
        self._client.connect("localhost", 1883)
        self._client.loop_forever()
