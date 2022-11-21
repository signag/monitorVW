#!/usr/bin/python3
"""
Module monitorVW

This module periodically reads data from Volkswagen WeConnect
and and stores specific car data in an InfluxDB or a CVS file
"""

import time
import datetime
import math
import os.path
import json
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS
from weconnect.NativeAPI import WeConnect
from weconnect.NativeAPI import VWError
from weconnect.vsr import VSR

# Set up logging
import logging
from logging.config import dictConfig
import logging_plus
logger = logging_plus.getLogger("main")

testRun = False
servRun = False

# Configuration defaults
cfgFile = ""
cfg = {
    "measurementInterval": 1800,
    "weconUsername" : None,
    "weconPassword" : None,
    "weconSPin" : None,
    "weconCarId" : None,
    "InfluxOutput" : False,
    "InfluxURL" : None,
    "InfluxOrg" : None,
    "InfluxToken" : None,
    "InfluxBucket" : None,
    "InfluxTripBucket" : None,
    "csvOutput" : False,
    "csvFile" : "",
    "carData" : []
}

# Constants
CFGFILENAME = "monitorVW.json"

def getCl():
    """
    getCL: Get and process command line parameters
    """

    import argparse
    import os.path

    global logger
    global testRun
    global servRun
    global cfgFile

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=
    """
    This program periodically reads data from VW WeConnect
    and stores these as measurements in an InfluxDB database.

    If not otherwises specified on the command line, a configuration file
       monitorVW.json
    will be searched sequentially under ./tests/data, $HOME/.config or /etc.

    This configuration file specifies credentials for WeConnect access,
    the car data to read, the connection to the InfluxDB and other runtime parameters.
    """
    )
    parser.add_argument("-t", "--test", action = "store_true", help="Test run - single cycle - no wait")
    parser.add_argument("-s", "--service", action = "store_true", help="Run as service - special logging")
    parser.add_argument("-l", "--log", action = "store_true", help="Shallow (module) logging")
    parser.add_argument("-L", "--Log", action = "store_true", help="Deep logging")
    parser.add_argument("-F", "--Full", action = "store_true", help="Full logging")
    parser.add_argument("-p", "--logfile", help="path to log file")
    parser.add_argument("-f", "--file", help="Logging configuration from specified JSON dictionary file")
    parser.add_argument("-v", "--verbose", action = "store_true", help="Verbose - log INFO level")
    parser.add_argument("-c", "--config", help="Path to config file to be used")

    args = parser.parse_args()

    # Disable logging
    logger = logging_plus.getLogger("main")
    logger.addHandler(logging.NullHandler())
    fLogger = logging_plus.getLogger(WeConnect.__module__)
    fLogger.addHandler(logging.NullHandler())
    vLogger = logging_plus.getLogger(VSR.__module__)
    vLogger.addHandler(logging.NullHandler())
    rLogger = logging_plus.getLogger()
    rLogger.addHandler(logging.NullHandler())

    # Set handler and formatter to be used
    handler = logging.StreamHandler()
    if args.logfile:
        handler = logging.FileHandler(args.logfile)
    formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
    formatter2 = logging.Formatter('%(asctime)s %(name)-33s %(levelname)-8s %(message)s')
    handler.setFormatter(formatter)

    if args.log:
        # Shallow logging
        handler.setFormatter(formatter2)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

    if args.Log:
        # Deep logging
        handler.setFormatter(formatter2)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        fLogger.addHandler(handler)
        fLogger.setLevel(logging.DEBUG)
        vLogger.addHandler(handler)
        vLogger.setLevel(logging.DEBUG)

    if args.Full:
        # Full logging
        handler.setFormatter(formatter2)
        rLogger.addHandler(handler)
        rLogger.setLevel(logging.DEBUG)
        # Activate logging of function entry and exit
        logging_plus.registerAutoLogEntryExit()

    if args.file:
        # Logging configuration from file
        logDictFile = args.file
        if not os.path.exists(logDictFile):
            raise ValueError("Logging dictionary file from command line does not exist: " + logDictFile)

        # Load dictionary
        with open(logDictFile, 'r') as f:
            logDict = json.load(f)

        # Set config file for logging
        dictConfig(logDict)
        logger = logging.getLogger()
        # Activate logging of function entry and exit
        #logging_plus.registerAutoLogEntryExit()

    # Explicitly log entry
    if args.Log or args.Full:
        logger.logEntry("getCL")
    if args.log:
        logger.debug("Shallow logging (main only)")
    if args.Log:
        logger.debug("Deep logging")
    if args.file:
        logger.debug("Logging dictionary from %s", logDictFile)

    if args.verbose or args.service:
        if not args.log and not args.Log and not args.Full:
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            fLogger.addHandler(handler)
            fLogger.setLevel(logging.WARNING)
            vLogger.addHandler(handler)
            vLogger.setLevel(logging.WARNING)

    if args.test:
        testRun = True

    if args.service:
        servRun = True

    if testRun:    
        logger.debug("Test run mode activated")
    else:
        logger.debug("Test run mode deactivated")
        
    if servRun:    
        logger.debug("Service run mode activated")
    else:
        logger.debug("Service run mode deactivated")

    if args.config:
        cfgFile = args.config
        logger.debug("Config file: %s", cfgFile)
    else:
        logger.debug("No Config file specified on command line")

    if args.Log or args.Full:
        logger.logExit("getCL")

def getConfig():
    """
    Get configuration for fritzToInfluxHA
    """
    global cfgFile
    global cfg
    global logger

    # Check config file from command line
    if cfgFile != "":
        if not os.path.exists(cfgFile):
            raise ValueError("Configuration file from command line does not exist: ", cfgFile)
        logger.info("Using cfgFile from command line: %s", cfgFile)

    if cfgFile == "":
        # Check for config file in ./tests/data directory
        curDir = os.path.dirname(os.path.realpath(__file__))
        curDir = os.path.dirname(curDir)
        cfgFile = curDir + "/tests/data/" + CFGFILENAME
        if not os.path.exists(cfgFile):
            # Check for config file in /etc directory
            logger.info("Config file not found: %s", cfgFile)
            cfgFile = ""

    if cfgFile == "":
        # Check for config file in home directory
        homeDir = os.environ['HOME']
        cfgFile = homeDir + "/.config/" + CFGFILENAME
        if not os.path.exists(cfgFile):
            # Check for config file in /etc directory
            logger.info("Config file not found: %s", cfgFile)
            cfgFile = "/etc/" + CFGFILENAME
            if not os.path.exists(cfgFile):
                logger.info("Config file not found: %s", cfgFile)
                cfgFile = ""

    if cfgFile == "":
        # No cfg available 
        logger.info("No config file available. Using default configuration")
    else:
        logger.info("Using cfgFile: %s", cfgFile)
        with open(cfgFile, 'r') as f:
            conf = json.load(f)
            if "measurementInterval" in conf:
                cfg["measurementInterval"] = conf["measurementInterval"]
            if "weconUsername" in conf:
                cfg["weconUsername"] = conf["weconUsername"]
            if "weconPassword" in conf:
                cfg["weconPassword"] = conf["weconPassword"]
            if "weconSPin" in conf:
                cfg["weconSPin"] = conf["weconSPin"]
            if "weconCarId" in conf:
                cfg["weconCarId"] = conf["weconCarId"]
            if "InfluxOutput" in conf:
                cfg["InfluxOutput"] = conf["InfluxOutput"]
            if "InfluxURL" in conf:
                cfg["InfluxURL"] = conf["InfluxURL"]
            if "InfluxOrg" in conf:
                cfg["InfluxOrg"] = conf["InfluxOrg"]
            if "InfluxToken" in conf:
                cfg["InfluxToken"] = conf["InfluxToken"]
            if "InfluxBucket" in conf:
                cfg["InfluxBucket"] = conf["InfluxBucket"]
            if "InfluxTripBucket" in conf:
                cfg["InfluxTripBucket"] = conf["InfluxTripBucket"]
            if "csvOutput" in conf:
                cfg["csvOutput"] = conf["csvOutput"]
            if "csvFile" in conf:
                cfg["csvFile"] = conf["csvFile"]
            if cfg["csvFile"] == "":
                cfg["csvOutput"] = False
            if "carData" in conf:
                cfg["carData"] = conf["carData"]
                
    # Check WeConnect credentials
    if not cfg["weconUsername"]:
        raise ValueError("weconUsername not specified")
    if not cfg["weconPassword"]:
        raise ValueError("weconPassword not specified")
    if not cfg["weconSPin"]:
        raise ValueError("weconSPin not specified")
    if not cfg["weconCarId"]:
        raise ValueError("weconCarId not specified")
    if (isinstance(cfg["weconSPin"], int)):
        cfg["weconSPin"] = str(cfg["weconSPin"]).zfill(4)
    if (isinstance(cfg["weconSPin"], str)):
        if (len(cfg["weconSPin"]) != 4):
            raise ValueError('Wrong S-PIN format: must be 4-digits')
        try:
            d = int(cfg["weconSPin"])
        except ValueError:
            raise ValueError('Wrong S-PIN format: must be 4-digits')
    else:
        raise ValueError('Wrong S-PIN format: must be 4-digits')

    logger.info("Configuration:")
    logger.info("    measurementInterval:%s", cfg["measurementInterval"])
    logger.info("    weconUsername:%s", cfg["weconUsername"])
    logger.info("    weconPassword:%s", cfg["weconPassword"])
    logger.info("    weconSPin:%s", cfg["weconSPin"])
    logger.info("    weconCarId:%s", cfg["weconCarId"])
    logger.info("    InfluxOutput:%s", cfg["InfluxOutput"])
    logger.info("    InfluxURL:%s", cfg["InfluxURL"])
    logger.info("    InfluxOrg:%s", cfg["InfluxOrg"])
    logger.info("    InfluxToken:%s", cfg["InfluxToken"])
    logger.info("    InfluxBucket:%s", cfg["InfluxBucket"])
    logger.info("    InfluxTripBucket:%s", cfg["InfluxTripBucket"])
    logger.info("    csvOutput:%s", cfg["csvOutput"])
    logger.info("    csvFile:%s", cfg["csvFile"])
    logger.info("    carData:%s", len(cfg["carData"]))

def waitForNextCycle():
    """
    Wait for next measurement cycle.

    This function assures that measurements are done at specific times depending on the specified interval
    In case that measurementInterval is an integer multiple of 60, the waiting time is calculated in a way,
    that one measurement is done every full hour.
    """
    global cfg

    if (cfg["measurementInterval"] % 60 == 0)\
    or (cfg["measurementInterval"] % 120 == 0)\
    or (cfg["measurementInterval"] % 240 == 0)\
    or (cfg["measurementInterval"] % 300 == 0)\
    or (cfg["measurementInterval"] % 360 == 0)\
    or (cfg["measurementInterval"] % 600 == 0)\
    or (cfg["measurementInterval"] % 720 == 0)\
    or (cfg["measurementInterval"] % 900 == 0)\
    or (cfg["measurementInterval"] % 1200 == 0)\
    or (cfg["measurementInterval"] % 1800 == 0):
        tNow = datetime.datetime.now()
        seconds = 60 * tNow.minute
        period = math.floor(seconds/cfg["measurementInterval"])
        waitTimeSec = (period + 1) * cfg["measurementInterval"] - (60 * tNow.minute + tNow.second + tNow.microsecond / 1000000)
        logger.debug("At %s waiting for %s sec.", datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S,"), waitTimeSec)
        time.sleep(waitTimeSec)
    elif (cfg["measurementInterval"] % 2 == 0)\
      or (cfg["measurementInterval"] % 4 == 0)\
      or (cfg["measurementInterval"] % 5 == 0)\
      or (cfg["measurementInterval"] % 6 == 0)\
      or (cfg["measurementInterval"] % 10 == 0)\
      or (cfg["measurementInterval"] % 12 == 0)\
      or (cfg["measurementInterval"] % 15 == 0)\
      or (cfg["measurementInterval"] % 20 == 0)\
      or (cfg["measurementInterval"] % 30 == 0):
            tNow = datetime.datetime.now()
            seconds = 60 * tNow.minute + tNow.second
            period = math.floor(seconds/cfg["measurementInterval"])
            waitTimeSec = (period + 1) * cfg["measurementInterval"] - seconds
            logger.debug("At %s waiting for %s sec.", datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S,"), waitTimeSec)
            time.sleep(waitTimeSec)
    else:
        waitTimeSec =cfg["measurementInterval"]
        logger.debug("At %s waiting for %s sec.", datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S,"), waitTimeSec)
        time.sleep(waitTimeSec)

def storeCarStatusData(mTS, vin, status, csvOut, influxOut, csvPath, influxWriteAPI, influxOrg, influxBucket):
    """
    Store car status data in InfluxDB or file

    The following car data are handled:
    +----------------+-----------+-----------------------------------------------------------+
    | name           | type      | Source                                                    |
    +----------------+-----------+-----------------------------------------------------------+
    | vin            | tag       | car.vehicleIdentificationNumber                           |
    | mileage        | field     | vsr.status.distance_covered                               |
    - tempOutside    | field     | vsr.status.temperature_outside                            |
    | fuelLevel      | field     | vsr.status.fuel_level                                     |
    - fuelMethod     | tag       | vsr.status.fuel_method ('0':'measured', '1':'calculated') |
    | stateOfCharge  | field?    | vsr.status.state_of_charge                                |
    """
    sep = ";"
    measurement = "carStatus"

    mileage = status.get('distance_covered','UNKNOWN')
    if mileage == "UNKNOWN":
        mileageInt = None
        mileagePr = ""
    else:
        mileageInt = int(mileage)
        mileagePr = mileage
        
    fuelLevel = status.get('fuel_level','UNKNOWN')
    if fuelLevel == "UNKNOWN":
        fuelLevelInt = None
        fuelLevelPr = ""
    else:
        fuelLevelInt = int(fuelLevel.split(" ")[0])
        fuelLevelPr = format(fuelLevelInt)
        
    stateOfCharge = status.get('state_of_charge','UNKNOWN')
    if stateOfCharge == "UNKNOWN":
        stateOfChargeInt = None
        stateOfChargePr = ""
    else:
        stateOfChargeInt = int(stateOfCharge.split(" ")[0])
        stateOfChargePr = format(stateOfChargeInt)
    
    if influxOut:
        point = influxdb_client.Point(measurement) \
            .time(mTS, influxdb_client.WritePrecision.MS) \
            .tag("vin", vin) \
            .field("mileage", mileageInt) \
            .field("fuelLevel", fuelLevelInt) \
            .field("stateOfCharge", stateOfChargeInt)
        influxWriteAPI.write(bucket=influxBucket, org=influxOrg, record=point)
        logger.debug("car status data written to InfluxDB")
        
    
    if csvOut:
        title = "_measurement" +  sep + "_time" + sep + "vin" + sep + "mileage" + sep + "fuelLevel" + sep + "stateOfCharge" + "\n"
        data = measurement + sep + mTS+ sep + vin + sep + mileagePr + sep + fuelLevelPr + sep + stateOfChargePr + "\n"
        writeCsv(csvPath, title, data)
        logger.debug("car status data written to csv file")
    
def writeCsv(fp, title, data):
    """
    Write data to CVS file
    """
    f = None
    newFile=True
    if os.path.exists(fp):
        newFile = False
    if newFile:
        f = open(fp, 'w')
    else:
        f = open(fp, 'a')
    logger.debug("File opened: %s", fp)

    if newFile:
        f.write(title)
    f.write(data)
    f.close()

def storeTripData(vwc, vin, type, conf, influxWriteAPI, influxOrg, influxBucket):
    """
    Store trip data in InfluxDB and/or file 
    """
    f = None
    if conf["InfluxOutput"] or conf["csvOutput"]:
        if conf["InfluxOutput"]:
            measurement = "trip_" + type
            timeStartDates = "1900-01-01"
            if "InfluxTimeStart" in conf:
                if conf["InfluxTimeStart"]:
                    if len(conf["InfluxTimeStart"]) > 0:
                        timeStartDates = conf["InfluxTimeStart"]
            timeStartDate = datetime.datetime.fromisoformat(timeStartDates)
            timePeriods = "9999"
            if "InfluxDaysBefore" in conf:
                    if conf["InfluxDaysBefore"]:
                        if len(conf["InfluxDaysBefore"]) > 0:
                            timePeriods = conf["InfluxDaysBefore"]
            timePeriod = int(timePeriods)
            timeStartPeriod = datetime.datetime.utcnow() - datetime.timedelta(days=timePeriod)
            
            timeStart = timeStartDate
            if timeStartPeriod > timeStart:
                timeStart = timeStartPeriod

        if conf["csvOutput"]:
            fp = conf["csvFile"]
            f = None
            newFile=True
            if os.path.exists(fp):
                newFile = False
            if newFile:
                f = open(fp, 'w')
                titleRequired = True
            else:
                f = open(fp, 'a')
                titleRequired = False
            logger.debug("File opened for csv output: %s", fp)
        
        logger.debug("getting trip data")    
        td = vwc.get_trip_data(theVin, type)
        trips = td['tripDataList']['tripData']
        logger.debug("%s trips revceived", str(len(trips)))
        for trip in trips:
            if conf["InfluxOutput"]:
                ts = trip["timestamp"][0:10]
                if datetime.datetime.fromisoformat(ts) >= timeStart:
                    tripToInflux(measurement, vin, trip, influxWriteAPI, influxOrg, influxBucket)
            if conf["csvOutput"]:
                tripToCsv(trip, f, titleRequired)
                titleRequired = False
        if f:
            f.close()
            logger.debug("File closed: %s", fp)
                
def tripToInflux(measurement, vin, trip, influxWriteAPI, influxOrg, influxBucket):
    """
    Store trip data in Influx
    """
    # Calculate consumption per trip not per 100km
    mileage = trip["mileage"]
    avElPwCons = trip["averageElectricEngineConsumption"]/10
    avFuelCons = trip["averageFuelConsumption"]/10
    electricPowerConsumed = avElPwCons * mileage / 100
    fuelConsumed = avFuelCons * mileage / 100
    point = influxdb_client.Point(measurement) \
        .time(trip["timestamp"], influxdb_client.WritePrecision.MS) \
        .tag("vin", vin) \
        .tag("tripID", trip["tripID"]) \
        .tag("reportReason", trip["reportReason"]) \
        .field("startMileage", trip["startMileage"]) \
        .field("tripMileage", trip["mileage"]) \
        .field("traveltime", trip["traveltime"]) \
        .field("electricPowerConsumed", electricPowerConsumed) \
        .field("fuelConsumed", fuelConsumed)

    influxWriteAPI.write(bucket=influxBucket, org=influxOrg, record=point)
    logger.debug("trip written to InfluxDB: %s (%s)", trip["tripID"], trip["timestamp"])

def tripToCsv(trip, fil, titleRequired):
    """
    Write trip to CVS file
    """
    sep = ";"
    if titleRequired:
        title = ""
        for f in trip:
            title = title + f + sep
        title = title[0:len(title)-1] + "\n"
        fil.write(title)
    
    data = ""
    for f in trip:
        data = data + format(trip[f]) + sep
    data = data[0:len(data)-1] + "\n"
    fil.write(data)
    logger.debug("trip written to csv file")
    
def instWeConnect():
    """
    Instantiate connection to WE Connect
    """
    # Log in to WeConnect
    userName = cfg["weconUsername"]
    password = cfg["weconPassword"]
    pin = cfg["weconSPin"]
    logger.debug("Instantiating WeConnect vwc")
    vwc = WeConnect(userName, password, pin)
    logger.debug("WeConnect vwc instantiated")
    vwc.login()
    logger.debug("WeConnect login successful")
    
    # Get car to query
    theCar = None
    logger.debug("Searching car in registered cars")
    cars = vwc.get_real_car_data()
    if (cars and len(cars)):
        for car in cars.get('realCars',[]):
            vin = car.get('vehicleIdentificationNumber','UNKNOWN')
            logger.debug("Found %s", vin)
            if vin == cfg["weconCarId"]:
                theCar = car
    else:
        raise VWError("No cars registered at WeConnect for specified profile")
    
    if theCar:
        logger.debug("getting theVin")
        theVin = theCar.get('vehicleIdentificationNumber','UNKNOWN')
        logger.debug("got theVin %s", theVin)
        return vwc, theVin
    else:
        raise VWError("Requested car not registered at WeConnect")

#============================================================================================
# Start __main__
#============================================================================================
#
# Get Command line options
getCl()

logger.info("=============================================================")
logger.info("monitorVW started")
logger.info("=============================================================")

# Get configuration
getConfig()

fb = None
influxClient = None
influxWriteAPI = None

try:
    # Instatntiate InfluxDB access
    if cfg["InfluxOutput"]:
        influxClient = influxdb_client.InfluxDBClient(
            url=cfg["InfluxURL"],
            token=cfg["InfluxToken"],
            org=cfg["InfluxOrg"]
        )
        influxWriteAPI = influxClient.write_api(write_options=SYNCHRONOUS)
        logger.debug("Influx interface instantiated")
    
except Exception as error:
    logger.critical("Unexpected Exception (%s): %s", error.__class__, error.__cause__)
    logger.critical("Unexpected Exception: %s", error.message)
    logger.critical("Could not get InfluxDB access")
    stop = True
    vwc = None
    influxClient = None
    influxWriteAPI = None


noWait = False
stop = False
failcount = 0
loggedIn = False
vwc = None
while not stop:
    try:
        # Wait unless noWait is set in case of VWError.
        # Skip waiting for test run
        if not noWait and not testRun:
            waitForNextCycle()
        noWait = False

        local_datetime = datetime.datetime.now()
        local_datetime_timestamp = float(local_datetime.strftime("%s"))
        UTC_datetime_converted = datetime.datetime.utcfromtimestamp(local_datetime_timestamp)
        mTS = UTC_datetime_converted.strftime("%Y-%m-%dT%H:%M:%S.%f000Z")
        
        # Log In to WE Connect
        if not loggedIn:
            logger.debug("Login to WeConnect required")
            [vwc, theVin] = instWeConnect()
            loggedIn = True
            logger.debug("Login successful")

        # Store car data
        logger.debug("getting status list")
        theVsr = vwc.get_vsr(theVin)
        thePvsr = vwc.parse_vsr(theVsr)
        theStatus = thePvsr.get('status',[])
        logger.debug("got theStatus")
        logger.debug("storing car status data")
        storeCarStatusData(mTS, theVin, theStatus, cfg["csvOutput"], cfg["InfluxOutput"], cfg["csvFile"], influxWriteAPI, cfg["InfluxOrg"], cfg["InfluxBucket"])
        
        if "carData" in cfg:
            cfgc = cfg["carData"]
            # Store short term trip data
            if "tripDataShortTerm" in cfgc:
                logger.debug("storing trip data shortTerm")
                storeTripData(vwc, theVin, "shortTerm", cfgc["tripDataShortTerm"], influxWriteAPI, cfg["InfluxOrg"], cfg["InfluxTripBucket"])
            
            # Store long term trip data
            if "tripDataLongTerm" in cfgc:
                logger.debug("storing trip data longTerm")
                storeTripData(vwc, theVin, "longTerm", cfgc["tripDataLongTerm"], influxWriteAPI, cfg["InfluxOrg"], cfg["InfluxTripBucket"])
            
            # Store cyclic trip data
            if "tripDataCyclic" in cfgc:
                logger.debug("storing trip data cyclic")
                storeTripData(vwc, theVin, "cyclic", cfgc["tripDataCyclic"], influxWriteAPI, cfg["InfluxOrg"], cfg["InfluxTripBucket"])

        if testRun:
            # Stop in case of test run
            stop = True

    except VWError as error:
        if loggedIn:
            # if already logged in to WEConnect, it may be possible that the automatic forced login 
            # was not successful. Therefore re-instantiate vwc and try again without waiting
            logger.warning("Unexpected VWError: %s", error.message)
            logger.warning("Trying to immediately re-instantiate WE Connect handle vwc")
            if vwc:
                del vwc
                vwc = None
            loggedIn = False
            stop = False
            noWait = True
        else:
            # exception occured during login
            # wait a cycle an try again
            logger.warning("Unexpected VWError: %s", error.message)
            logger.warning("Trying to re-instantiate WE Connect handle vwc in next cycle")
            if vwc:
                del vwc
                vwc = None
            loggedIn = False
            noWait = False
            stop = False
            failcount = failcount + 1
            if failcount > 10:
                stop = True
                logger.critical("Could not establish connection to WE Connect after %s tries", failcount)
                logger.critical("Stopping")
                if vwc:
                    del vwc
                if influxClient:
                    del influxClient
                if influxWriteAPI:
                    del influxWriteAPI

    except Exception as error:
        stop = True
        logger.critical("Unexpected Exception (%s): %s", error.__class__, error.__cause__)
        if vwc:
            del vwc
        if influxClient:
            del influxClient
        if influxWriteAPI:
            del influxWriteAPI
        raise error

    except KeyboardInterrupt:
        stop = True
        logger.debug("KeyboardInterrupt")
        if vwc:
            del vwc
        if influxClient:
            del influxClient
        if influxWriteAPI:
            del influxWriteAPI

logger.info("=============================================================")
logger.info("monitorVW terminated")
logger.info("=============================================================")
