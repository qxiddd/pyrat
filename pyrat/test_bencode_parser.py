#!/usr/bin/python3

import unittest
from .bencode_parser import Decoder, Encoder

class TestBencode(unittest.TestCase):
    def test_parse_unknown_token(self):
        d = Decoder(b"I123e")
        with self.assertRaises(RuntimeError):
            d.parse()

    def test_parse_int(self):
        d = Decoder(b"i123e")
        self.assertEqual(d.parse(), 123)
        d.reset()
        self.assertEqual(d.parse_int(), 123)

    def test_parse_str(self):
        d = Decoder(b"13:Hello, world!")
        self.assertEqual(d.parse(), b"Hello, world!")
        d.reset()
        self.assertEqual(d.parse_string(), b"Hello, world!")

    def test_parse_str_idx_out_of_range(self):
        d = Decoder(b"14:Hello, world!")
        with self.assertRaises(IndexError):
            d.parse()

    def test_parse_str_bad_token(self):
        d = Decoder(b"14?Hello, world!")
        with self.assertRaises(RuntimeError):
            d.parse()

    def test_parse_list(self):
        d = Decoder(b"li123e13:Hello, world!e")
        self.assertEqual(d.parse(), [123, b"Hello, world!"])
        d.reset()
        self.assertEqual(d.parse_list(), [123, b"Hello, world!"])

    def test_parse_dict(self):
        d = Decoder(b"d4:key16:value14:key2i123ee")
        self.assertEqual(d.parse(), {b"key1": b"value1", b"key2": 123})
    
    def test_parse_nothing(self):
        d = Decoder(b"")
        with self.assertRaises(EOFError):
            d.parse()


class TestEncoder(unittest.TestCase):
    def test_encode_string(self):
        self.assertEqual(Encoder.encode_strint("Hello, world!"),
            b"13:Hello, world!")

    def test_encode_int(self):
        self.assertEqual(Encoder.encode_int(42), b"i42e")
        
    def test_encode_list(self):
        self.assertEqual(Encoder.encode_list([123, b"Hello, world!"]),
            b"li123e13:Hello, world!e")

    def test_encode_bytes(self):
        self.assertEqual(Encoder.encode_bytes(b"kek"), b"3:kek")

    def test_encode_dict(self):
        d = {b"key1": b"value1", b"key2": 123}
        self.assertEqual(Encoder.encode_dict(d), 
            b"d4:key16:value14:key2i123ee")

    def test_encode_unknown(self):
        with self.assertRaises(TypeError) as smth:
            Encoder.encode(smth)

if __name__ == "__main__":
    unittest.main()

