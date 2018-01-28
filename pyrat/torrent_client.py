#!/usr/bin/python3


import asyncio
from hashlib import sha1
import time

from .tracker_client import TrackerClient
from .torrent_file import TorrentInfo
from .piece_manage import PiecesManager
from .protocol import PeerConnection



MAX_PEERS = 1


class TorrentClient:
    def __init__(self, torrent_file):
        self._tinfo = TorrentInfo(torrent_file)
        self._tracker = TrackerClient(self._tinfo)
        self._peers_queue = asyncio.Queue()
        self._workers = list()
        self._futures = list()
        self._piece_manager = PiecesManager(self._tinfo)
        self._aborted = False

    async def start(self):
        self._init_workers()
        previous = None # time we last made an announce call (timestamp)
        interval = 30 * 60 # default interval between requests
        while True:
            if self._piece_manager.complete:
                print("Done")
                break
            if self._aborted:
                print("Aborted")
                break
            current = time.time()
            if (not previous) or (previous + interval < current):
                response = await self._tracker.connect(
                    first=True if not previous else False,
                    uploaded=self._piece_manager.bytes_uploaded,
                    downloaded=self._piece_manager.bytes_downloaded,
                    next_url=True)
                if not response:
                    print("Tracker doesn't responds")
                else:
                    previous = time.time()
                    interval = response.interval
                    self._empty_queue()
                    local_time = time.localtime() 
                    for peer in response.peers:
                        self._peers_queue.put_nowait(peer)
                    print("Tracker respond got at {}. " \
                          "Next request in {} minutes.".format(
                              "{}:{}".format(local_time.tm_hour,
                                             local_time.tm_min),
                              interval / 60))
                    print(response)
            else:
                await asyncio.sleep(5)
        self.stop()

    def _init_workers(self):
        self._workers = [PeerConnection(self._peers_queue,
                                        self._tinfo.hash,
                                        self._tracker.my_id,
                                        self._piece_manager,
                                        worker_id,
                                        self._on_block_retrieved)
                         for worker_id in range(MAX_PEERS)]
        # self._futures = [worker.future for worker in self._workers]

    @property
    def future(self):
        return self._future

    def _empty_queue(self):
        while not self._peers_queue.empty():
            self._peers_queue.get_nowait()

    def stop(self):
        print("Aborting!")
        self._aborted = True
        for worker in self._workers:
            worker.stop()
        self._piece_manager.close()
        self._tracker.close()

    def _on_block_retrieved(self, peer_id, piece_index, block_offset, data):
        self._piece_manager.block_received(peer_id=peer_id,
                                           piece_idx=piece_index,
                                           block_offset=block_offset,
                                           data=data)

