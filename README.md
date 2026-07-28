# 🚋 `TORminal`

`TORminal` is a terminal-based dashboard for monitoring public transport using GTFS and GTFS-Realtime data.

It provides a convenient way to track selected bus and tram lines, stops, schedules, and live departure information. 
The goal is to have a convenient way of looking up frequently used connections without checking individual stops or routes in separate apps or websites.
`TORminal` runs in your terminal, is lightweight and distraction-free and features a TUI.

For now it only supports Poznań based public transport lines. 🐐

## Installation

`TORminal` can be installed as a standalone command using `uv`:

    uv tool install git+https://github.com/marchmare/torminal.git

After installation, run:

    torminal

## Usage

### TUI app

By default, `TORminal` is meant to be used as TUI run on a local machine.

#### Implemented features:

* real-time departure monitoring with ETA and delay status on a virtual bollards
* adding/removing queries via modal screens

#### Known issues:

* removing queries may occasionally blank the screen — switching windows and back restores it

#### Not yet implemented:

* 'Options' and 'About' screens
* trip details modal

### Kiosk mode

Kiosk mode runs `TORminal` with a single-column layout and auto-scrolling, suitable for headless machines or public displays.

To enable kiosk mode, run:

    torminal --headless

New queries can be added from a remote session without restarting the dashboard:

    ssh user@host torminal -a <stop_code> <route_id>

## FAQ

* **How to differentiate stop codes?**

    For now, only ZTM Poznań data can be monitored using `TORminal`. 
ZTM Poznań indexes stops using an integer or a stop code. 
Stop codes can be found either on a reallife printed timetables for a stop or on timetables for specific route published by [mpk.poznan.pl](https://mpk.poznan.pl) (for example [Most Teatralny MT44](https://www.mpk.poznan.pl/przystanek/?linia=3&data=&przystanek=5&kierunek=0)).
Currently, there's no other known, convenient or automated way to do this.

## Devtools

`TORminal`'s TUI is built with [`textual`](https://textual.textualize.io/) library. 

To debug while `TORminal` is running, first open and keep this debug console running:

    textual console

In another console, run `TORminal` with this snippet:

    uv run textual run --dev torminal.cli:app
