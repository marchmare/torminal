import asyncio

from torminal.gtfs.static import GTFSStaticLoader
from torminal.query import Monitor, Query
from torminal.gtfs.realtime import fetch_gtfs_rt_feed, fetch_peka_vm_feed
from torminal.requests import HTTPXCLIENT


async def main() -> None:
    async with HTTPXCLIENT:
        print("🚋 TORminal")
        loader = GTFSStaticLoader(print_update)
        dataset = await loader.load()
        print(dataset.feed_info)  # print feed_info to see if dataset applies for today's date

        # initialize monitor
        monitor = Monitor(dataset)

        monitor.add_query(Query("NARA71", "10"))
        monitor.add_query(Query("NARA71", "3"))
        monitor.add_query(Query("NARA71", "214"))

        # get peka feeds in parallel
        peka_tasks = {stop: fetch_peka_vm_feed(monitor.dataset.stops.get(stop)) for stop in monitor.matched_queries}
        peka_results = await asyncio.gather(*peka_tasks.values())
        peka_feeds = dict(zip(peka_tasks.keys(), peka_results))

        # poll:
        rt_gtfs = await fetch_gtfs_rt_feed()
        for stop, stop_matches in monitor.matched_queries.items():
            rt_msg = peka_feeds[stop]
            for match in stop_matches:
                rt_tu = rt_gtfs.trip_updates.get(match.trip.id, None)
                rt_vp = rt_gtfs.vehicle_positions.get(match.trip.id, None)

                result = monitor.poll(match, rt_tu, rt_vp, rt_msg)
                print(result)


def app() -> None:
    asyncio.run(main())


def print_update(progress):
    print(progress)
