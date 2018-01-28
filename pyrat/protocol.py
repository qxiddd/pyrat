
import asyncio 
from struct import pack, unpack
from concurrent.futures import CancelledError
from collections import namedtuple
from bitstring import BitArray



class ProtocolError(Exception):
    pass


class PeerState:
    def __init__(self, choked: bool, interested: bool):
        self.choked = choked
        self.interested = interested


REQUEST_SIZE = 2**14 # 2 KiB
Peer = namedtuple("Peer", ['ip', 'port', 'id'])

    
class PeerConnection:
    def __init__(self, queue: asyncio.Queue, info_hash,
                 my_peer_id, piece_manager, worker_id: int, on_block_cb=None):
        self._queue = queue
        self._info_hash = info_hash
        self._my_id = my_peer_id
        self._piece_manager = piece_manager
        self._on_block_cb = on_block_cb
        self.worker_id = worker_id

        self._defaults()
        self._aborted = False
        self._future = asyncio.ensure_future(self._start())

    def _defaults(self):
        self._my_state = PeerState(choked=True, interested=True)
        self._peer_state = PeerState(choked=False, interested=False)
        self._peer = None
        self._writer = None
        self._reader = None
        self._pending = False
        

    async def _start(self):
        while not self._aborted:
            peer_ip, peer_port = await self._queue.get()
            try:
                self._reader, self._writer = await asyncio.open_connection(
                    peer_ip, peer_port)
                print("Connected to {}".format(peer_ip))
                buff = await self._handshake(peer_ip, peer_port)
                print('Handshake sended')
                await self._send_interested()
                print('Interested sended')
                async for msg in PeerStreamIterator(self._reader, buff):
                    if self._aborted:
                        break
                    if type(msg) is BitField:
                        self._piece_manager.add_peer(self._peer.id,
                                                     msg.bitfield)
                    elif type(msg) is Interested:
                        self._peer_state.interested = True
                    elif type(msg) is NotInterested:
                        self._peer_state.interested = False
                    elif type(msg) is Choke:
                        self._my_state.choked = True
                    elif type(msg) is Unchoke:
                        self._my_state.choked = False 
                    elif type(msg) is Have:
                        self._piece_manager.update_peer(self._peer.id,
                                                       msg.index)
                    elif type(msg) is KeepAlive:
                        pass
                    elif type(msg) is Piece:
                        self._pending = False
                        self._on_block_cb(
                            peer_id=self._peer.id,
                            piece_idx=msg.index,
                            block_offset=msg.begin,
                            data=msg.block)
                    elif type(msg) is Request:
                        oass  # TODO Not sharing
                    elif type(msg) is Cancel:
                        pass  # TODO Not sharing
                    if not self._my_state.choked:
                        if self._my_state.interested:
                            if not self._pending:
                                self._pending = True
                                await self._request_piece()
            except ProtocolError as e:
                print("Protocol Errore")
            except (ConnectionRefusedError, TimeoutError):
                print("Unnable to connect to {}".format(peer_ip))
            except (ConnectionResetError, CancelledError):
                print("Connection closed")
            except Exception as e:
                print("An error occured")
                self.cancel()
                self._future = None
                raise e

            if self._writer:    
                self._writer.close()
            self._defaults()

    def cancel(self):
        if self._writer:
            self._writer.close()

    def stop(self):
        self._aborted= True
        if not self.future.done():
            self.future.cancel()

    async def _request_piece(self):
        block = self._piece_manager.next_request(self._peer.id)
        if block:
            msg = Request(block.piece, block.offset, block.length).encode()
            self._writer.write(msg)
            await self._writer.drain()

    async def _handshake(self, peer_ip, peer_port):
        msg = Handshake(self._info_hash, self._my_id).encode()
        self._writer.write(msg)
        await self._writer.drain()
        buf = ''
        while len(buf) < Handshake.length:
            buf = await self._reader.read(PeerStreamIterator.CHUNK_SIZE)
        response = Handshake.decode(buf[:Handshake.length])
        if not response:
            raise ProtocolError("Unable receive and parse a handshake")
        if response.info_hash != self._info_hash:
            raise ProtocolError("Handshake with invalid info_hash")
        self._peer = Peer(peer_ip, peer_port, response.peer_id)
        return buf[Handshake.length:]

    async def _send_interested(self):
        msg = Interested().encode()
        self._writer.write(msg)
        await self._writer.drain()


class PeerStreamIterator:

    CHUNK_SIZE = 10*1024

    def __init__(self, reader, init_buff: bytes=None):
        self._reader = reader
        self._buffer = init_buff if init_buff else None

    async def __aiter__(self):
        return self

    async def __anext__(self):
        while True:
            try:
                data = await self._reader.read(PeerStreamIterator.CHUNK_SIZE)
                if data:
                    self._buffer += data
                    msg = self.parse()
                    if msg: return msg
                else:
                    if self._buffer:
                        msg = self.parse()
                        if msg: return msg
                    raise StopAsyncIteration()
            except ConnectionResetError:
                print("Connection closed by peer")
                raise StopAsyncIteration()
            except CancelledError:
                raise StopAsyncIteration()
            except Exception:
                print("Error when iterating over stream!")
                raise StopAsyncIteration()
        raise StopAsyncIteration()

    def parse(self):
        header_length = 4
        if not len(self._buffer) > 4:
            return None
        msg_length = unpack('>I', self._buffer[0:4])[0]
        if msg_length == 0:
            return KeepAlive()
        if len(self._buffer) < msg_length:
            print("Not enough data got")
            return None
        msg_id = unpack(">b", self._buffer[4:5])[0]

        def _consume():
            self._buffer = self._buffer[header_length + msg_length:]

        def _data():
            return self._buffer[:header_length + msg_length]

        if msg_id is PeerMessage.BitField:
            data = _data()
            _consume()
            return BitField.decode(data)
        elif msg_id is PeerMessage.Interested:
            _consume()
            return Interested()
        elif msg_id is PeerMessage.NotInterested:
            _consume()
            return NotInterested()
        elif msg_id is PeerMessage.Choke:
            _consume()
            return Choke()
        elif msg_id is PeerMessage.Unchoke:
            _consume()
            return Unchoke()
        elif msg_id is PeerMessage.Have:
            data = _data()
            _consume()
            return Have.decode(data)
        elif msg_id is PeerMessage.Piece:
            data = _data()
            _consume()
            return Piece.decode(data)
        elif msg_id is PeerMessage.Request:
            data = _data()
            _consume()
            return Request.decode(data)
        elif msg_id is PeerMessage.Cancel:
            data = _data()
            _consume()
            return Cancel.decode(data)
        print("Unknown msg type got")


class PeerMessage:

    Choke = 0
    Unchoke = 1
    Interested = 2
    NotInterested = 3
    Have = 4
    BitField = 5
    Request = 6
    Piece = 7
    Cancel = 8
    Port = 9

    def encode(self) -> bytes:
        raise NotImplementedError()

    @classmethod
    def decode(self, data: bytes):
        raise NotImplementedError()


class Handshake(PeerMessage):
    
    pstr = "BitTorrent protocol"
    length = 49 + len(pstr) # 68

    def __init__(self, info_hash: bytes, peer_id: bytes):
        self._info_hash = info_hash
        self._peer_id = peer_id if isinstance(peer_id, bytes) \
            else bytes(peer_id, "UTF-8")

    @property
    def info_hash(self):
        return self._info_hash

    @property
    def peer_id(self):
        return self._peer_id

    def encode(self):
        return pack(
            '>B19s8x20s20s',
            19, b"BitTorrent protocol",
            self._info_hash, self._peer_id)

    @classmethod
    def decode(cls, data: bytes):
        if len(data) < (49 + 19):
            return None
        parts = unpack('>B19s8x20s20s', data)
        return cls(info_hash=parts[2], peer_id=parts[3])
       
    def __str__(self):
        return "Handshake from" + self._peer_id.decode("UTF-8")


class KeepAlive(PeerMessage):
    def encode(self):
        return pack(">B", 0)

    @classmethod
    def decode(cls):
        return cls()

    def __str__(self):
        return "KeepAlive"


class BitField(PeerMessage):
    def __init__(self, data):
        self.bitfield = BitArray(bytes=data)

    def encode(self):
        bits_length = len(self.bitfield.bytes)
        return pack(">Ib" + bits_length + "s",
                    1 + bits_length,
                    PeerMessage.BitField,
                    self.bitfield.bytes)

    @classmethod
    def decode(cls, data: bytes):
        msg_length = unpack(">I", data[:4])[0]
        parts = unpack('>Ib' + str(msg_length - 1) + 's', data)
        return cls(parts[2])

    def __str__(self):
        return "BitField"


class Interested(PeerMessage):
    def encode(self):
        return pack('>Ib',
                    1,  # Message length
                    PeerMessage.Interested)

    @classmethod
    def decode(cls, data):
        return cls()

    def __str__(self):
        return 'Interested'


class NotInterested(PeerMessage):
    def encode(self):
        return pack('>Ib',
                    1,  # Message length
                    PeerMessage.NotInterested)

    @classmethod
    def decode(cls, data):
        return cls()

    def __str__(self):
        return 'NotInterested'


class Choke(PeerMessage):
    def encode(self):
        return pack('>Ib',
                    1,  # Message length
                    PeerMessage.Choke)

    @classmethod
    def decode(cls, data):
        return cls()

    def __str__(self):
        return 'Choke'


class Unchoke(PeerMessage):
    def encode(self):
        return pack('>Ib',
                    1,  # Message length
                    PeerMessage.Unchoke)

    @classmethod
    def decode(cls, data):
        return cls()

    def __str__(self):
        return 'Unchoke'


class Have(PeerMessage):
    def __init__(self, index):
        self.index = index

    def encode(self):
        return pack(">IbI",
                    5, # Message length
                    PeerMessage.Have,
                    self.index)
    @classmethod
    def decode(cls, data: bytes):
        idx = unpack(">IbI", data)[2]
        return cls(idx)

    def __str__(self):
        return "Have index: " + str(self.index)


class Request(PeerMessage):
    def __init__(self, index: int, begin: int, length = REQUEST_SIZE):
        self.index = index
        self.begin = begin
        self.length = length

    def encode(self):
        return pack(">IbIII",
                    13, # Message length
                    PeerMessage.Request,
                    self.index,
                    self.begin,
                    self.length)

    @classmethod
    def decode(cls, data: bytes):
        parts = unpack(">IbIII", data)
        return cls(parts[2], parts[3], parts[4])

    def __str__(self):
        return "Request"


class Piece(PeerMessage):

    length = 9  # The Piece message length without the block data

    def __init__(self, index: int, begin: int, block: bytes):
        self.index = index
        self.begin = begin
        self.block = block
    
    def encode(self):
        blk_length = len(self.block)
        msg_length = Piece.length + blk_length
        return pack(">IbII" + str(blk_length) + "s",
                    msg_length,
                    PeerMessage.Piece,
                    self.index,
                    self.begin,
                    self.block)

    @classmethod
    def decode(cls, data: bytes):
        length = unpack('>I', data[:4])[0]
        parts = unpack(">IbII" + str(length - Piece.length) + "s",
                       data[:length+4])
        return cls(parts[2], parts[3], parts[4])

    def __str__(self):
        return "Piece"


class Cancel(PeerMessage):
    def __init__(self, index, begin, length: int = REQUEST_SIZE):
        self.index = index
        self.begin = begin
        self.length = length

    def encode(self):
        return pack(">IbIII",
                    13, # Message length
                    PeerMessage.Cancel,
                    self.index,
                    self.begin,
                    self.length)

    @classmethod
    def decode(self, data: bytes):
        parts = unpack(">IbIII", data)
        return cls(parts[2], parts[3], parts[4])
    
    def __str__(self):
        return "Cancel"

