import os
import requests
from stellar_base.horizon import Horizon
from ipfs_utils import *
import base64

SMART_ACCOUNT_ADDRESS = os.environ.get('SMART_ACCOUNT_ADDRESS')
HORIZON_ADDRESS = os.environ.get('HORIZON_ADDRESS')

horizon = Horizon(HORIZON_ADDRESS)

smart_account = horizon.account(SMART_ACCOUNT_ADDRESS)

hash_file = upload_file_to_ipfs("./sample_get_vote_input_file.json")
worker_1_peer_address = base64.b64decode(smart_account['data']['worker_1_peer_address']).decode()
result = requests.get("http://" + worker_1_peer_address + '/api/smart_program/' + SMART_ACCOUNT_ADDRESS,
                      params={"input_file_hash": hash_file})

print(result.text)
