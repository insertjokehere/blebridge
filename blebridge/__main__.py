from bluepy.btle import Scanner, DefaultDelegate
import schedule
from threading import Thread
from time import sleep
import logging
import sys
from . import drivers, mqtt

logger = logging.getLogger(__name__)
devices = {}


class ScanDelegate(DefaultDelegate):
    def __init__(self, mqtt_host):
        DefaultDelegate.__init__(self)
        self.mqtt_host = mqtt_host

    def handleDiscovery(self, dev, isNewDev, isNewData):
        global devices
        if isNewDev:
            driver = drivers.Driver.for_scan_result(dev)
            if driver is not None:
                device = driver(dev, self.mqtt_host)
                logger.debug("Discovered device {}, using driver {}".format(dev.addr, driver))
                if device.update_every is not None:
                    schedule.every(device.update_every.seconds).seconds.do(device.do_update)
                    device.do_update_once()
                devices[dev.addr] = device
            else:
                logger.debug("Discovered device {}, but no driver available".format(dev.addr))
        else:
            if dev.addr in devices:
                devices[dev.addr].scan_update(dev)


class ScanThread(Thread):

    def __init__(self, *args, **kwargs):
        self.mqtt_host = None
        Thread.__init__(self, *args, **kwargs)

    def run(self):
        scanner = Scanner().withDelegate(ScanDelegate(self.mqtt_host))
        scanner.start()
        while True:
            try:
                scanner.process(timeout=5)
            except:
                scanner.stop()
                raise


class UpdateThread(Thread):

    def run(self):
        schedule.run_all()
        while True:
            schedule.run_pending()
            sleep(1)


scan_thread = ScanThread(daemon=True)
update_thread = UpdateThread(daemon=True)

def mqtt_on_connect(client, userdata, flags, rc):
    scan_thread.mqtt_host = client
    scan_thread.start()
    update_thread.start()


def main():
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format="%(asctime)s [%(name)s] - %(message)s")

    try:
        host = mqtt.MQTTHost(mqtt_on_connect)
        host.start()
    finally:
        if scan_thread.is_alive():
            scan_thread.join()
        if update_thread.is_alive():
            update_thread.join()


main()
