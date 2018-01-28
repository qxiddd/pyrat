
import aiohttp
from random import randint
from socket import inet_ntoa
from struct import unpack
from urllib.parse import urlencode

from .bencode_parser import Decoder, Encoder


class TrackerResponce:
    def __init__(self, responce: dict):
       self._responce = responce

    @property
    def failure(self) -> str:
        if b'failure reason' in self._responce:
            return self._responce[b'failure reason'].decode('utf-8')

    @property
    def interval(self) -> int: 
        return self._responce.get(b'interval', 0)

    @property
    def complete(self) -> int:
        return self._responce.get(b'complete', 0)

    @property
    def incomplete(self) -> int:
        return self._responce.get(b'incomplete', 0)

    @property
    def peers(self):
        peers = self._responce[b'peers']
        if type(peers) == list: # List of dicts
            # Not sure it's correct
            return [(peer[b'ip'], peer[b'port']) for peer in peers]
        else:
            peers = [peers[i:i+6] for i in range(0, len(peers), 6)]
            return [(inet_ntoa(peer[:4]), unpack(">H", peer[4:])[0])
                    for peer in peers]
    
    def __str__(self):
        return "incomplete: {incomplete}\n" \
               "complete: {complete}\n" \
               "interval: {interval}\n" \
               "peers: {peers}\n".format(
                incomplete=self.incomplete,
                complete=self.complete,
                interval=self.interval,
                peers=", ".join([x for (x, _) in self.peers]))
    

class TrackerClient:
    def __init__(self, tfile):
        self._torrent = tfile
        self._my_id = '-PC0516-' + ''.join(
            [str(randint(0, 9)) for _ in range(12)])
        self._http_client = aiohttp.ClientSession()
        
    async def connect(self,
                      first: bool=False,
                      uploaded: int=0,
                      downloaded: int=0,
                      next_url: bool=False):
        args = {
            'info_hash': self._torrent.hash,
            'peer_id': self._my_id,
            'port': 6889,
            'uploaded': uploaded,
            'downloaded': downloaded,
            'left': self._torrent.total_size - downloaded,
            'compact': 1
        }
        if first: args['event'] = 'started'
        url = self._torrent.get_announce(next_url) + '?' + urlencode(args)
        try:
            async with self._http_client.get(url) as responce:
                if not responce.status == 200:
                    raise ConnectionError("Can not connect to tracker")
                data = await responce.read()
                return TrackerResponce(Decoder(data).parse())
        except aiohttp.client_exceptions.ClientConnectionError:
            return None
        
    def close(self):
        self._http_client.close()

    @property
    def my_id(self):
        return self._my_id

