import json
import tempfile
from stellar_base.horizon import Horizon
from stellar_base.keypair import Keypair
from stellar_base.memo import *
from stellar_base.operation import *
from stellar_base.transaction import Transaction
from stellar_base.transaction_envelope import TransactionEnvelope as Te
from ipfs_utils import *

IPFS_ADDRESS = os.environ.get('IPFS_ADDRESS')
HORIZON_ADDRESS = os.environ.get('HORIZON_ADDRESS')
NETWORK_PASSPHRASE = os.environ.get('NETWORK_PASSPHRASE')
SMART_ACCOUNT_ADDRESS = os.environ.get('SMART_ACCOUNT_ADDRESS')
USER_SECRET_KEY = os.environ.get('USER_SECRET_KEY')

horizon = Horizon(HORIZON_ADDRESS)

latest_ledger = horizon.ledgers(order='desc', limit=1)
TRANSACTION_BASE_FEE = latest_ledger['_embedded']['records'][0]['base_fee_in_stroops']

smart_account_info = horizon.account(SMART_ACCOUNT_ADDRESS)
smart_account_data = smart_account_info['data']

smart_account_keypair = Keypair.from_address(SMART_ACCOUNT_ADDRESS)
user_keypair = Keypair.from_seed(USER_SECRET_KEY)

execution_base_fee = base64.b64decode(smart_account_data['execution_fee']).decode()
execution_base_fee_in_xlm = int(execution_base_fee) / 10000000

operations = [
    Payment(destination=smart_account_keypair.address().decode(), amount='1', asset=Asset("XLM"))
]

input_file_hash = upload_file_to_ipfs("./input_file_sample.json")

execution_config = {
    "input_file": input_file_hash,
    "base_state": base64.b64decode(horizon.account(smart_account_keypair.address().decode())['data']
                                   ['current_state']).decode()
}
temp_execution_config_file = tempfile.mkstemp()
with open(temp_execution_config_file[1], 'w') as f:
    json.dump(execution_config, f)
execution_config_file_hash = upload_file_to_ipfs(temp_execution_config_file[1])
execution_config_file_hex = ipfs_hash_to_base58(execution_config_file_hash)

tx = Transaction(
    source=user_keypair.address().decode(),
    sequence=horizon.account(user_keypair.address().decode()).get('sequence'),
    fee=int(TRANSACTION_BASE_FEE) * len(operations),
    operations=operations,
    memo=HashMemo(execution_config_file_hex)
)

envelope = Te(tx=tx, network_id=NETWORK_PASSPHRASE)
envelope.sign(Keypair.from_seed(user_keypair.seed()))
horizon.submit(envelope.xdr())
