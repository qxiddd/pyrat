True

from collections import OrderedDict



TOKEN_INT = b'i'
TOKEN_LIST = b'l'
TOKEN_DICT = b'd'
TOKEN_END = b'e'
TOKEN_STR_SEPARATOR = b':'


class Decoder:
    def __init__(self, data):
        self._data = data
        self._idx = 0

    def _is_out_of_range(self, idx: int):
        return idx >= len(self._data)

    def _peek(self):
        """
        Return current char from data or None if eol
        """
        return None if self._is_out_of_range(self._idx + 1) \
            else self._data[self._idx: self._idx+1]

    def _read_next(self, length: int):
        if self._idx + length > len(self._data):
            raise IndexError()
        res = self._data[self._idx: self._idx + length]
        self._idx += length
        return res
            
    def _read_until(self, token: bytes):
        try:
            occurrence = self._data.index(token, self._idx)
            res = self._data[self._idx: occurrence]
            self._idx = occurrence + 1
            return res
        except ValueError:
            raise RuntimeError("Can't find token {}.".format(str(token)))

    def reset(self):
        self._idx = 0

    def parse(self):
        c = self._peek()
        if c is None:
            raise EOFError("Unexpected EOF")
        if c == TOKEN_END:
            return None
        if c in b'0123456789':
            return self.parse_string()
        if c == TOKEN_INT:
            return self.parse_int()
        if c == TOKEN_LIST:
            return self.parse_list()
        if c == TOKEN_DICT:
            return self.parse_dict()
        else:
            raise RuntimeError("Unknown token \"{}\" got at {}".format(
                c, self._idx)
            )

    def parse_string(self):
        bytes_to_read = int(self._read_until(TOKEN_STR_SEPARATOR))
        return self._read_next(bytes_to_read)

    def parse_int(self):
        self._idx += 1 # Token
        return int(self._read_until(TOKEN_END))

    def parse_list(self):
        self._idx += 1 # Token
        res = list()
        while self._data[self._idx: self._idx + 1] != TOKEN_END:
            res.append(self.parse())
        self._idx += 1 # END tocken
        return res

    def parse_dict(self):
        self._idx += 1 # Token
        res = dict()
        while self._data[self._idx: self._idx + 1] != TOKEN_END:
            key = self.parse_string()
            obj = self.parse()
            res[key] = obj
        self._idx += 1 # END tocken
        return res


class Encoder:
    @staticmethod
    def encode(data):
        if type(data) == str:
            return Encoder.encode_strint(data)
        if type(data) == int:
            return Encoder.encode_int(data)
        if type(data) == list:
            return Encoder.encode_list(data)
        if type(data) == dict or type(data) == OrderedDict:
            return Encoder.encode_dict(data)
        if type(data) == bytes:
            return Encoder.encode_bytes(data)
        raise TypeError("Got unknown type: {}.".format(type(data)))

    @staticmethod
    def encode_strint(data: str):
        return bytes("{}:{}".format(len(data), data), "UTF-8")

    @staticmethod
    def encode_int(data: int):
        return bytes("i{}e".format(data), "UTF-8")

    @staticmethod
    def encode_list(data: list):
        res = bytearray('l', 'utf-8')
        res += b''.join([Encoder.encode(item) for item in data])
        res += b'e'
        return res 

    @staticmethod
    def encode_dict(data: dict or OrderedDict):
        res = bytearray('d', 'utf-8')
        for k, v in data.items():
            key = Encoder.encode(k)
            value = Encoder.encode(v)
            if key and value:
                res += key
                res += value
            else:
                raise RuntimeError('Bad dict')
        res += b'e'
        return res 

    @staticmethod
    def encode_bytes(data: bytes):
        return str.encode(str(len(data))) + b":" + data

