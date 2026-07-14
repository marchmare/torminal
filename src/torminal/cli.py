from torminal.gtfs.static import GTFSStaticLoader
from torminal.query import Monitor, Query
from torminal.tui.main import WelcomeApp


def app() -> None:
    print("🚋 TORminal")
    # app = WelcomeApp()
    # app.run()

    loader = GTFSStaticLoader(print_update)
    lookup = loader.load()
    query = Query("NARA71", 10, 60)
    monitor = Monitor(lookup)
    result = monitor.poll(query)
    for r in result:
        print("\nDEPARTURE:")
        print(r)


def print_update(progress):
    print(progress)
