import base58
from binascii import hexlify, unhexlify
import ipfshttpclient
import os

IPFS_ADDRESS = os.environ.get('IPFS_ADDRESS')


def upload_file_to_ipfs(file):
    with ipfshttpclient.connect(IPFS_ADDRESS) as client:
        hash = client.add(file)['Hash']
    return hash


def ipfs_hash_to_base58(hash):
    base58_decoded = base58.b58decode(hash)
    return hexlify(base58_decoded).decode()[4:]
