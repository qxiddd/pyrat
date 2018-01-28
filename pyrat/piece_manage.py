
from hashlib import sha1
from collections import defaultdict
import time
import logging
import math
import os

from .protocol import REQUEST_SIZE



class Block:
    Missing = 0
    Pending = 1
    Retrieved = 2

    def __init__(self, piece_idx: int, offset: int, length: int):
        self.piece_idx = piece_idx
        self.offset = offset
        self.length = length
        self.status = Block.Missing
        self.data = None


class Piece:
    def __init__(self, index: int, blocks: [], hash_value):
        self._idx = index
        self._blocks = blocks
        self._hash = hash_value

    @property
    def index(self):
        return self._idx

    def reset(self):
        for block in self._blocks:
            block.status = Block.Missing

    def next_req(self):
        missing = [b for b in self.blocks if b.status is Block.Missing]
        if missing:
            missing[0].status = Block.Pending
            return missing[0]
        return None

    def block_received(self, offset: int, data: bytes):
        matches = [b for b in self.blocks if b.offset == offset]
        block = matches[0] if matches else None
        if block:
            block.status = Block.Retrieved
            block.data = data
        else:
            logging.warning('Trying to complete a non-existing block {offset}'
                            .format(offset=offset))

    @property
    def is_complete(self):
        not_complete = [b for b in self._blocks if b.status == Block.Retrieved]
        return not not_complete

    @property
    def is_hash_matching(self):
        piece_hash = sha1(self.data).digest()
        return self._hash == piece_hash

    @property
    def data(self):
        retrieved = sorted(self.blocks, key=lambda b: b.offset)
        blocks_data = (b.data for b in retrieved)
        return b''.join(blocks_data)
    

class PiecesManager:
    def __init__(self, torrent_info):
        self._tinfo = torrent_info
        self._peers_maps = dict() # peer_id => pieces_map: bitfield
        self._pieces_prevalence = defaultdict(int)
        self._pending_blocks_reqs = []
        self._pending_pieces = []
        self._missing_pieces = []
        self._complete_pieces = []
        self._max_pending_time = 300 * 1000 # 5 minutes

        self._missing_pieces = self._init_pieces()
        self._fds = self._init_fds() # file descriptors
        
    def _init_fds(self):
        fd = os.open(self._tinfo.filename,  os.O_RDWR | os.O_CREAT)
        return [fd]
        #TODO Rewrite to multifile mode

    def close(self):
        for fd in self._fds:
            os.close(fd)

    def _write(self, piece):   
        pos = piece.index * self.torrent.piece_length
        os.lseek(self._fds[0], pos, os.SEEK_SET)
        os.write(self._fds[0], piece.data)
        #TODO Rewrite to multifile mode

    def _init_pieces(self):
        pieces = []
        number_of_std_block = math.ceil(self._tinfo.piece_length / REQUEST_SIZE)
        for idx, hash_value in enumerate(self._tinfo.pieces_hashes):
            if idx < (self._tinfo.total_pieces - 1):
                blocks = [Block(idx, offset * REQUEST_SIZE, REQUEST_SIZE)
                          for offset in range(number_of_std_block)]
            else:
                last_piece_length = self._tinfo.total_size % \
                                        self._tinfo.piece_length
                num_blocks = math.ceil(last_piece_length / REQUEST_SIZE)
                blocks = [Block(idx, offset * REQUEST_SIZE, REQUEST_SIZE)
                          for offset in range(num_blocks)]
                if last_piece_length % REQUEST_SIZE > 0:
                    blocks[-1].length = last_piece_length % REQUEST_SIZE
            pieces.append(Piece(idx, blocks, hash_value))
        return pieces

    @property
    def complete(self):
        return len(self._complete_pieces) == self._tinfo.piece_length
    
    @property
    def bytes_downloaded(self):
        return len(self._complete_pieces) * self._tinfo.piece_length

    @property
    def bytes_uploaded(self):
        return 0
        # TODO add support for sending

    def add_peer(self, peer_id, pieces_map: list):
        self._peers_maps[peer_id] = pieces_map
        for piece_idx in pieces_map:
            self._pieces_prevalence[piece_idx] += 1

    def update_peer(self, peer_id, piece_idx):
        if peer_id in self._peers_maps:
            self._peers_maps[peer_id] = True
            self._pieces_prevalence[peer_id] += 1
    
    def remove_peer(self, peer_id):
        if peer_id in self._peers_maps:
            for piece_idx in self._pieces_prevalence:
                if piece_idx in self._peers_maps[peer_id]:
                    self._pieces_prevalence[piece_idx] -= 1
            del self._peers_maps[peer_id]

    def block_received(self, peer_id, piece_idx, block_offset, data):
        for idx, req in enumerate(self._pending_blocks_reqs):
            if req.block.piece_idx == piece_idx and \
               req.block.offset == block_offset:
                del self._pending_blocks_reqs[idx]
        ps = [p for p in self._pending_pieces if p.index == piece_idx]
        piece = piece[0] if ps else None
        if piece:
            piece.block_received(block_offset, data)
            if piece.is_complete:
                if piece.is_hash_matching:
                    self._write(piece)
                    self._pending_pieces.remove(piece)
                    self._complete_pieces.append(piece)
                else:
                    piece.reset()

    def next_request(self, peer_id):
        if peer_id not in self._peers_maps:
            return None

        block = self._expired_requests(peer_id)
        if not block:
            block = self._next_ongoing(peer_id)
            if not block:
                block = self._next_missing(peer_id)
        return block

    def _expired_requests(self, peer_id):
        # Rerequest a long-expected block
        curr_time = int(round(time.time()))
        for req in self._pending_blocks_reqs:
            if self._peers_maps[peer_id][req.block.piece_idx]:
                if req.added + self._max_pending_time < curr_time:
                    req.added = curr_time
                    return req.block
        return None
           
    def _next_ongoing(self, peer_id):
        # Request next block for some ongoing piece
        for piece in self._pending_pieces:
            if self._peers_maps[peer_id][piece.index]:
                b = piece.next_req()
                if b:
                    curr_time = int(round(time.time() * 1000))
                    self._pending_blocks_reqs.append(
                        PendingRequest(b, curr_time))
                    return b
        return None
           
    def _next_missing(self, peer_id):
        rarest_pieces = sorted(self._missing_pieces,
                               key=lambda p: self._pieces_prevalence[p.index])
        for piece in rarest_pieces:
            if self._peers_maps[peer_id][piece.index]:
                self._missing_pieces.remove(piece)
                self._pending_pieces.append(piece)
                return piece.next_req()
        return None
           
