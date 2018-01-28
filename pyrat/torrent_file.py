
from .bencode_parser import Decoder, Encoder
from hashlib import sha1
import math



class TFile:
    def __init__(self, path, length, attr=b''):
        self._path = list(map(lambda v: v.decode(), path))
        self._length = length
        self._attr = attr

    @property
    def name(self):
        return "/".join(self._path)

    @property
    def path(self):
        yield from self._path

    @property
    def length(self):
        return self._length

    @property
    def attribute(self):
        return self._attr

    @staticmethod
    def from_dict(d: dict):
        if b'attr' in d: return TFile(d[b'path'], d[b'length'], d[b'attr'])
        return TFile(d[b'path'], d[b'length'])

    def __str__(self):
        res = "File: \"{}\"\nlenght: {}".format(self.name, self.length) 
        if self._attr: res += "\nattribute: " + self._attr.decode()
        return res


class TorrentInfo:
    def __init__(self, filename):
        self._files = list()
        with open(filename, mode="rb") as f:
            tfile_data = f.read()
            self._data = Decoder(tfile_data).parse()
            info = Encoder.encode(self._data[b"info"])
            self._info_hash = sha1(info)
            self._identify_files()
            self._take_announce()
    
    @property
    def multi_file(self):
        return b"files" in self._data[b"info"]

    def _identify_files(self):
        self._filename = self._data[b'info'][b'name']
        if self.multi_file:
            self._files.extend(
                (TFile.from_dict(x) for x in self._data[b'info'][b"files"])
            )
        else:
            self._files.append(
                TFile([self._filename], self._data[b'info'][b'length'])
            )

    def _take_announce(self):
        self._announce_idx = 0
        self._announce_list = [self._data[b"announce"].decode('utf-8')]
        if b"announce-list" in self._data:
            for ann in self._data[b'announce-list']:
                ann = ann[0].decode("utf-8")
                if ann not in self._announce_list:
                    self._announce_list.append(ann)

    @property
    def files(self):
        yield from self._files

    @property
    def filename(self):
        return self._filename.decode('utf-8')

    def get_announce(self, next_ann=False):
        if next_ann:
            self._announce_idx = (self._announce_idx + 1) % \
                len(self._announce_list)
        return self._announce_list[self._announce_idx]

    @property
    def hex_hash(self):
        return self._info_hash.hexdigest()

    @property
    def hash(self):
        return self._info_hash.digest()

    @property
    def piece_length(self):
        return self._data[b'info'][b'piece length']

    @property
    def total_size(self):
        res = 0
        for i in self.files: res += i.length
        return res

    @property
    def pieces_hashes(self):
        offset = 0
        size = len(self._data[b'info'][b'pieces'])
        while offset < size:
            yield self._data[b'info'][b'pieces'][offset: offset + 20]
            offset += 20

    @property
    def total_pieces(self):
        return math.ceil(self.total_size / self.piece_length)

    def __str__(self):
        res = "Name: {}\n" \
            "Total size: {}\n" \
            "Hash: {}\n" \
            "Announce URL: {}\n" \
            "Files:".format(self.filename, self.total_size,
                self.hex_hash, self.get_announce())
        for f in self.files:
            res += "\n\tPath: \"{}\"\n\tLength: {}".format(f.name, f.length)
            if f.attribute:
                res += "\n\tAttribute: {}".format(f.attribute.decode('utf-8'))
            res += "\n"
        return res

