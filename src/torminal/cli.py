from google.transit import gtfs_realtime_pb2
from .parser import load_lookup


def main() -> None:
    print("🚋 TORminal")

    # get lookup dictionaries
    lookup = load_lookup()

    # summary
    print("Loaded data summary:")
    print(f"\t ⬩ vehicles: {len(lookup['vehicles'])}")
    print(f"\t ⬩ trips: {len(lookup['trips'])}")
    print(
        f"\t ⬩ trip stops: {len(lookup['trip_stops'])} -> "
        f"{sum(len(ts.items) for ts in lookup['trip_stops'].values())} events"
    )
    print(f"\t ⬩ stops definitions: {len(lookup['stops'])}")
    print(f"\t ⬩ trip routes definitions: {len(lookup['routes'])}")
    print(
        f"\t ⬩ trip shapes definitions: {len(lookup['shapes'])} -> "
        f"{sum(len(p.items) for p in lookup['shapes'].values())} points"
    )
