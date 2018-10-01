from bluepy.btle import Scanner, DefaultDelegate
import schedule
from threading import Thread
from time import sleep
import logging
import sys

logger = logging.getLogger(__name__)

from . import drivers

devices = {}


class ScanDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)

    def handleDiscovery(self, dev, isNewDev, isNewData):
        global devices
        if isNewDev:
            driver = drivers.Driver.for_scan_result(dev)
            if driver is not None:
                device = driver(dev)
                if device.update_every is not None:
                    schedule.every(device.update_every.seconds).seconds.do(device.update)
                devices[dev.addr] = device
                logger.debug("Discovered device {}, using driver {}".format(dev.addr, driver))
            else:
                logger.debug("Discovered device {}, but no driver available".format(dev.addr))
        else:
            if dev.addr in devices:
                devices[dev.addr].scan_update(dev)


class ScanThread(Thread):

    def run(self):
        scanner = Scanner().withDelegate(ScanDelegate())
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


def main():
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format="%(asctime)s [%(name)s] - %(message)s")

    scan_thread = ScanThread()
    scan_thread.start()

    update_thread = UpdateThread()
    update_thread.start()

    try:
        while True:
            sleep(1)
    finally:
        scan_thread.join()
        update_thread.join()


main()
