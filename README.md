# monitorVW

The program periodically reads car data from Volkswagen WeConnect and stores these as measurements in an InfluxDB database.

For WeConnect, see: <https://www.volkswagen-nutzfahrzeuge.de/de/digitale-dienste-und-apps/we-connect.html>

As interface to WeConnect Web ervices, I use <https://github.com/trocotronic/weconnect>

In order to use the program you need
- A registration at WeConnect
- An Influx DB V2.4 or later running on the same or another machine
- A Grafana instance vor visualization

InfluxDB (<https://www.influxdata.com/products/influxdb-overview/>) is a time series database which can be used as cloud version or local installation on various platforms.

For visualization with Grafana, see <https://grafana.com/>

## Getting started

| Step | Action                                                                                                                                       |
|------|----------------------------------------------------------------------------------------------------------------------------------------------|
| 1.   | Install **monitorVW** (```[sudo] pip install monitorVW```) on a Linux system (e.g. Raspberry Pi)                                             |
| 2.   | Install and configure an InfluxDB V2.4 (<https://docs.influxdata.com/influxdb/v2.4/install/>)                                                |
| 3.   | In InfluxDB, create a new bucket for status data (<https://docs.influxdata.com/influxdb/v2.4/organizations/buckets/create-bucket/>)          |
| 4.   | In InfluxDB, create a new bucket for trip data this should be different from status data because of longer retention period                  |
| 5.   | In InfluxDB, create an API Token with write access to the buckets (<https://docs.influxdata.com/influxdb/v2.4/security/tokens/create-token/>)|
| 6.   | Create and stage configuration file for **monitorVW** (see [Configuration](#configuration))                                                  |
| 7.   | Do a test run (see [Usage](#usage))                                                                                                          |
| 8.   | Set up **monitorVW** service (see [Serviceconfiguration](#serviceconfiguration))                                                             |

## Usage

```shell
usage: monitorVW.py [-h] [-t] [-s] [-l] [-L] [-F] [-f FILE] [-v] [-c CONFIG]

    This program periodically reads data from VW WeConnect
    and stores these as measurements in an InfluxDB database.

    If not otherwises specified on the command line, a configuration file
       monitorVW.json
    will be searched sequentially under ./tests/data, $HOME/.config or /etc.

    This configuration file specifies credentials for WeConnect access,
    the car data to read, the connection to the InfluxDB and other runtime parameters.


options:
  -h, --help            show this help message and exit
  -t, --test            Test run - single cycle - no wait
  -s, --service         Run as service - special logging
  -l, --log             Shallow (module) logging
  -L, --Log             Deep logging
  -F, --Full            Full logging
  -p, --logfile         path to log file
  -f FILE, --file FILE  Logging configuration from specified JSON dictionary file
  -v, --verbose         Verbose - log INFO level
  -c CONFIG, --config CONFIG
                        Path to config file to be used
```

## Configuration

Configuration for **monitorVW** needs to be provided in a specific configuration file.
By default, a configuration file "monitorVW.json" is searched under ```$HOME/.config``` or under ```/etc```.

For testing in a development environment, primarily the location ```../tests/data``` is searched for a configuration file.

Alternatively, the path to the configuration file can be specified on the command line.

### Structure of JSON Configuration File

The following is an example of a configuration file:
A a template can be found under
```./data``` in the installation folder.

```json
{
    "measurementInterval": 1800,
    "weconUsername": "weconUser",
    "weconPassword": "weconPwd",
    "weconSPin": "weconPin",
    "weconCarId": "weconCarID",
    "InfluxOutput": true,
    "InfluxURL": "influxURL",
    "InfluxOrg": "inflixOrg",
    "InfluxToken": "influxToken",
    "InfluxBucket": "influxBucket",
    "csvOutput": true,
    "csvFile": "tests/output/monitorVW.csv",
    "carData": {
        "tripDataShortTerm": {
            "InfluxOutput": true,
            "InfluxMeasurement": "tripShortTerm",
            "InfluxTimeStart": "",
            "InfluxDaysBefore": "5",
            "csvOutput": true,
            "csvFile": "tests/output/monitorVW_tripST.csv"
        },
        "tripDataLongTerm": {
            "InfluxOutput": false,
            "InfluxMeasurement": "tripLongTerm",
            "InfluxTimeStart": "2022-10-01",
            "InfluxDaysBefore": "",
            "csvOutput": true,
            "csvFile": "tests/output/monitorVW_tripLT.csv"
        },
        "tripDataCyclic": {
            "InfluxOutput": false,
            "InfluxMeasurement": "tripCyclic",
            "InfluxTimeStart": "2022-10-01",
            "InfluxDaysBefore": "",
            "csvOutput": true,
            "csvFile": "tests/output/monitorVW_tripCy.csv"
        }
    }
}
```

### Parameters

| Parameter               | Description                                                                                                       | Mandatory          |
|-------------------------|-------------------------------------------------------------------------------------------------------------------|--------------------|
| measurementInterval     | Measurement interval in seconds. (Default: 1800)                                                                  | No                 | 
| weconUsername           | User name of Volkswagen WE Connect registration                                                                   | Yes                |
| weconPassword           | Password of Volkswagen WE Connect registration                                                                    | Yes                |
| weconSPin               | The 4-digit security pin which is specified in the mobile We Connect App                                          | Yes                |
| weconCarId              | Vehicle Identification Number (VIN/FIN) as shown for cars registered in WE Connect                                | Yes                |
| InfluxOutput            | Specifies whether data shall be stored in InfluxDB (Default: false)                                               | No                 |
| InfluxURL               | URL for access to Influx DB                                                                                       | Only for Influx    |
| InfluxOrg               | Organization Name specified during InfluxDB installation                                                          | Only for Influx    |
| InfluxToken             | Influx API Token (see [Getting started](#gettingstarted))                                                         | Only for Influx    |
| InfluxBucket            | Bucket to be used for storage of car status data                                                                  | Only for Influx    |
| InfluxTripBucket        | Bucket to be used for storage of car trip data                                                                    | Only for Influx    |
| csvOutput               | Specifies whether car data shall be written to a csv file (Default: false)                                        | No                 |
| csvFile                 | Path to the csv file                                                                                              | For csvOutput=true |
| **carData**             | list of car data to be considered (default: Empty)                                                                | No                 |
| - **tripDataShortTerm** | Short term trip data (includes every individual trip)                                                             | Yes                |
| -- InfluxOutput         | Specifies whether trip data shall be written to InfluxDB                                                          | Yes                |
| -- InfluxMeasurement    | Measurement to be used for this kind of trip data                                                                 | Yes                |
| -- InfluxTimeStart      | Start date from which on trips shall be included (default: 01.01.1900)                                            | Yes                |
| -- InfluxDaysBefore     | Number of days before current date from which on trips shall be included (default: 9999) (later of both is uesd)  | Yes                |
| -- csvOutput            | Specifies whether these trip data shall be written to a cvs file                                                  | Yes                |
| -- csvFile              | File path to which these trip data shall be written                                                               | Yes                |
| - **tripDataLongTerm**  | Long term trip data (aggregated trip data for longer periods                                                      | No                 |
| - **tripDataCyclic**    | Aggregated trips from one fill-up to the next                                                                     | No                 |

## InfluxDB Data Schema
**monitorVW** uses the following schema when storing measurements in the database:

|Data Element              |Description                                                      |
|--------------------------|-----------------------------------------------------------------|
| _time                    | carStatus: timestamp when data is written to InfluxDB           |
|                          | trip     : timestamp when trip was ended                        |
| _measuerement            | "carStatus", "trip_shortTerm", "trip_longTerm", "trip_cyclic"   |
| **tags**                 |                                                                 |
| - vin                    | Car ID (vehicle identification number) - all measurements       |
| - tripID                 | We-Connect-internal ID for the trip - only trip measurements    |
| - reportReason           | We-Connect-internal reason for the trip - only trip measurements|
| **fields**               |                                                                 |
| - fuelLevel              | percentage of fuel filling - only for carStatus                 |
| - stateOfCharge          | percentage of charging of HV battery - only for carStatus       |
| - mileage                | current mileage - only for carStatus                            |
| - startMileage           | Mileage at trip start - only trip measurements                  |
| - tripMileage            | Mileage for the trip - only trip measurements                   |
| - travelTime             | Travel time (min) for trip - only trip measurements             |
| - fuelConsumed           | Fuel consumed (l) for trip - only trip measurements             |
| - electricPowerConsumed  | Electric power consumed (kWh) for trip - only trip measurements |

## Serviceconfiguration

To continuously log car data, **monitorVW** should be run as service.

A service configuration file template can be found under
```./data``` in the installation folder.

| Step | Action                                                                                             |
|------|----------------------------------------------------------------------------------------------------|
| 1.   | Adjust the service configuration file, if required, especially check python path and user          |
| 2.   | Stage configuration file: ```sudo cp monitorVW.service /etc/systemd/system ```                     |
| 3.   | Start service: ```sudo systemctl start monitorVW.service ```                                       |
| 4.   | Check log: ```sudo journalctl -e ``` should show that **monitorVW** has successfully started       |
| 5.   | In case of errors adjust service configuration file and restart service                            |
| 6.   | To enable your service on every reboot: ```sudo systemctl enable monitorVW.service```              |
