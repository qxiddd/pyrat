#!/usr/bin/python


from pprint import pprint
import sys
import asyncio
from argparse import ArgumentParser

from pyrat.torrent_file import TorrentInfo
from pyrat.bencode_parser import Decoder
from pyrat.tracker_client import TrackerClient
from pyrat.torrent_client import TorrentClient


# async def work():
    # a = TorrentInfo(sys.argv[1])
    # print(str(a))
    # print("Creating tracker")
    # tracker = TrackerClient(a)
    # response = await tracker.connect(first=True, next_url=False)
    # tracker.close()
    # print(response) if response else print("Server doesn't respond")

async def work():
    exception = None
    torrent = TorrentClient(sys.argv[1])
    try:
        await torrent.start()
    except Exception as e:
        print("Something went wrong")
        exception = e
    finally:
        torrent.stop()
        if exception: raise exception


def torrent():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(work())
    loop.close()

# a = TorrentInfo(sys.argv[1])
# pprint(list(a.pieces_hashes))


def init_parser():
    parser = ArgumentParser(description="PyRat torrent client.")
    parser.add_argument("sourse_file", action="store", help="Source torrent file.")
    parser.add_argument("-l", "--log-level", action='store', dest="log_lvl", 
                        default="CRITICAL", 
                        help="Logging level. Should be one of: CRITICAL, ERROR," \
                             "WARNING, INFO, DEBUG.")
    parser.add_argument("-f", "--log-output", action="store", dest="log_output",
                        default="NONE", help="Additional logging " \
                        "output. If NONE, program will do logging only to stdin.")
    return parser


def main():
    parser = init_parser()
    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(0)
    args = parser.parse_args()
    print(args)


if __name__ == "__main__":
    main()

