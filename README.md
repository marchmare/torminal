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

## Devtools

`TORminal`'s TUI is built with [`textual`](https://textual.textualize.io/) library. 

To debug while `TORminal` is running, first open and keep this debug console running:

    textual console

In another console, run `TORminal` with this snippet:

    uv run textual run --dev torminal.cli:app
