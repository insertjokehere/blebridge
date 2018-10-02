from schedule import CancelJob
from struct import unpack
from datetime import datetime, timedelta
from bluepy.btle import Peripheral, ADDR_TYPE_PUBLIC, BTLEException
from logging import getLogger


class Driver:

    DEFAULTS = {
        'update_every': None
    }

    @classmethod
    def for_scan_result(cls, result):
        if result.addrType == ADDR_TYPE_PUBLIC:
            if result.addr.startswith("c4:7c:8d:"):
                return MiFloraDriver
            else:
                return PresenceDriver

    def __init__(self, device, **kwargs):
        self.address = device.addr
        self.logger = getLogger(self.address)

        self.scan_update(device)

        self._config = kwargs
        for k, v in self.DEFAULTS.items():
            self._config.setdefault(k, v)

        self.update_every = self._config.get('update_every', None)
        if self.update_every is not None:
            self.update_every = timedelta(seconds=self.update_every)

    @property
    def peripheral(self):
        return Peripheral(self.address)

    def do_update(self):
        try:
            self.update()
        except:
            self.logger.exception("Update failed")

    def do_initial_update(self):
        self.do_update()
        return CancelJob

    def update(self):
        self.logger.warning("This device does not support periodic updates")

    def scan_update(self, result):
        self.rssi = result.rssi
        self.last_seen = datetime.now()
        self.logger.debug("Scan update, rssi {}dB".format(self.rssi))


class PresenceDriver(Driver):

    DEFAULTS = {
        'update_every': 60,
        'scan_timeout': 60
    }

    def __init__(self, *args, **kwargs):
        Driver.__init__(self, *args, **kwargs)
        self.present = True

    @property
    def scan_timeout(self):
        return timedelta(seconds=self._config['scan_timeout'])

    @property
    def has_timedout(self):
        return self.last_seen < datetime.now() - self.scan_timeout

    def update(self):
        if self.has_timedout and self._found:
            self.present = False
            self.logger.info("Device disappeared")

    def scan_update(self, result):
        Driver.scan_update(self, result)
        self.present = True

    def serialize(self):
        return {
            x: getattr(self, x) for x in [
                'present',
                'last_seen'
            ]
        }


class MiFloraDriver(Driver):

    HANDLE_READ_VERSION_BATTERY = 0x38
    HANDLE_READ_NAME = 0x03
    HANDLE_READ_SENSOR_DATA = 0x35
    HANDLE_WRITE_MODE_CHANGE = 0x33
    DATA_MODE_CHANGE = bytes([0xA0, 0x1F])

    DEFAULTS = {
        'update_every': 30 * 60  # Update every 30 mins by default
    }

    def __init__(self, *args, **kwargs):
        Driver.__init__(self, *args, **kwargs)

        self._fw_version_next_check = None
        self._fw_version = None
        self.battery = None
        self.temperature = None
        self.brightness = None
        self.moisture = None
        self.conductivity = None
        self.last_update = None

    @property
    def fw_version(self):
        # Only update firmware version/battery state every ~24 hours
        if self._fw_version_next_check is None or \
           self._fw_version_next_check < datetime.now():
            try:
                result = self.peripheral.readCharacteristic(self.HANDLE_READ_VERSION_BATTERY)
            except BTLEException:
                self.logger.exception("Failed to read firmware version")
                result = None

            if result:
                self.battery = result[0]
                self._fw_version = "".join([chr(x) for x in result[2:]])
                self._fw_version_next_check = datetime.now() + timedelta(hours=24)
            else:
                self._fw_version_next_check = datetime.now() + timedelta(minutes=5)

        return self._fw_version

    def serialize(self):
        return {
            x: getattr(self, x) for x in [
                'fw_version',
                'battery',
                'temperature',
                'brightness',
                'moisture',
                'conductivity',
                'last_update',
                'last_seen'
            ]
        }

    def update(self):
        if self.fw_version is None:
            self.logger.warning("Failed to fetch basic device details")
            return

        connection = self.peripheral
        if self.fw_version >= "2.6.6":
            try:
                connection.writeCharacteristic(self.HANDLE_WRITE_MODE_CHANGE, self.DATA_MODE_CHANGE, True)
            except BTLEException:
                self.logger.exception("Failed to put device into update mode")

        try:
            response = connection.readCharacteristic(self.HANDLE_READ_SENSOR_DATA)
        except BTLEException:
            self.logger.exception("Failed to read sensor data")

        if self._is_valid(response):
            temp, self.brightness, self.moisture, self.conductivity = unpack('<hxIBhxxxxxx', response)
            self.temperature = temp / 10.0
            self.last_update = datetime.now()
            self.logger.debug("Updated: {}".format(self.serialize()))

    def _is_valid(self, data):
        if data[7] > 100:
            return False
        elif self.fw_version >= "2.6.6" and sum(data[10:]) == 0:
            return False
        elif sum(data) == 0:
            return False
        else:
            return True
