from torminal.gtfs.static import GTFSStaticLoader
from torminal.query import Monitor, Query
from torminal.gtfs.realtime import fetch_gtfs_rt_feed, fetch_peka_vm_feed

from collections import defaultdict

# from torminal.tui.app import TORminal


def app() -> None:
    print("🚋 TORminal")
    # # app = TORminal()
    # app.run()
    loader = GTFSStaticLoader(print_update)
    dataset = loader.load()
    print(dataset.feed_info)  # print feed_info to see if dataset applies for today's date
    query = Query("NARA71", 10)
    monitor = Monitor(dataset)

    matches = monitor.resolve_query(query)

    # group by stops:
    matches_grouped = defaultdict(list)
    for match in matches:
        matches_grouped[match.stop.code].append(match)

    # poll:
    for stop, stop_matches in matches_grouped.items():
        rt_msg = fetch_peka_vm_feed(monitor.dataset.stops.get(stop))

        for match in stop_matches:
            rt_gtfs = fetch_gtfs_rt_feed()

            rt_tu, rt_vp = (
                rt_gtfs.trip_updates.get(match.trip.id, None),
                rt_gtfs.vehicle_positions.get(match.trip.id, None),
            )

            result = monitor.poll(match, rt_tu, rt_vp, rt_msg)
            print(result)


def print_update(progress):
    print(progress)
