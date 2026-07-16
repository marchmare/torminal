from torminal.gtfs.static import GTFSStaticLoader
from torminal.query import Monitor, Query
from torminal.tui.app import TORminal


def app() -> None:
    print("🚋 TORminal")
    # # app = TORminal()
    # app.run()
    loader = GTFSStaticLoader(print_update)
    lookup = loader.load()
    print(lookup.feed_info)
    query = Query("NARA71", 214, 60)
    monitor = Monitor(lookup)

    matches = monitor.resolve_query(query)

    for match in matches:
        result = monitor.poll(match)
        print(result)


def print_update(progress):
    print(progress)
