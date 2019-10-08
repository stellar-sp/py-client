import ipfshttpclient
import os
import requests
from stellar_base.horizon import Horizon
from stellar_base.transaction_envelope import TransactionEnvelope as Te
import threading
import stellar_base.transaction_envelope as TxEnv
import stellar_base.transaction as Tx
from stellar_base.operation import *
from stellar_base.keypair import Keypair
from stellar_base.transaction import Transaction
import json
import base64
import hashlib
from environs import Env
from stellar_base.memo import TextMemo

if os.path.exists('./.env'):
    env = Env()
    env.read_env(path="./.env")

IPFS_ADDRESS = os.environ.get('IPFS_ADDRESS')
HORIZON_ADDRESS = os.environ.get('HORIZON_ADDRESS')
NETWORK_PASSPHRASE = os.environ.get('NETWORK_PASSPHRASE')
SMART_ACCOUNT_ADDRESS = os.environ.get('SMART_ACCOUNT_ADDRESS')
USER_ACCOUNT_ADDRESS = os.environ.get('USER_ACCOUNT_ADDRESS')
USER_SECRET_KEY = os.environ.get('USER_SECRET_KEY')
RUNNING_PROGRAM_GAS_LIMIT = os.environ.get('RUNNING_PROGRAM_GAS_LIMIT')

horizon = Horizon(HORIZON_ADDRESS)

smart_account_info = horizon.account(SMART_ACCOUNT_ADDRESS)
smart_account_data = smart_account_info['data']
worker_addresses = []

execution_base_fee = base64.b64decode(smart_account_data['execution_base_fee']).decode()
execution_base_fee_in_xlm = int(execution_base_fee) / 10000000

tx = Transaction(
    source=USER_ACCOUNT_ADDRESS,
    sequence=horizon.account(USER_ACCOUNT_ADDRESS).get('sequence'),
    fee=1000,
    operations=[
        Payment(source=USER_ACCOUNT_ADDRESS, destination=SMART_ACCOUNT_ADDRESS, amount=str(execution_base_fee_in_xlm),
                asset=Asset("XLM"))],
    memo=TextMemo("exec_smart_program_base_fee")
)
te = Te(tx=tx, network_id=NETWORK_PASSPHRASE)
te.sign(Keypair.from_seed(USER_SECRET_KEY))
gas_pre_payed_tx_hash = horizon.submit(te.xdr()).get('hash')

counter = 1
while True:
    if 'worker_' + str(counter) + '_address' in smart_account_data:
        worker_addresses.append({
            'address': base64.b64decode(smart_account_data['worker_' + str(counter) + '_address']).decode(),
            'public_key': base64.b64decode(smart_account_data['worker_' + str(counter) + '_public_key']).decode()
        })
    else:
        break
    counter += 1

with ipfshttpclient.connect(IPFS_ADDRESS) as client:
    input_file_hash = client.add(os.getcwd() + "/input_file_sample.json")['Hash']

workers_results = []


class RunProgramThread(threading.Thread):
    def __init__(self, worker_address, sender_public_key):
        threading.Thread.__init__(self)
        self.worker_address = worker_address
        self.sender_public_key = sender_public_key

    def run(self):
        try:

            message = json.dumps({
                "input_file": input_file_hash,
                "gas_pre_payed_tx_hash": gas_pre_payed_tx_hash
            })

            message_hash = hashlib.sha256(str.encode(message)).hexdigest()
            signature = Keypair.from_seed(USER_SECRET_KEY).sign(str.encode(message_hash))

            res = requests.post(url=self.worker_address['address'], json={
                "message": message,
                "message_hash": message_hash,
                "signature": base64.b64encode(signature).decode(),
            })
            workers_results.append({
                "worker_address": self.worker_address,
                "result": res
            })
        except Exception as e:
            print(e)
            pass


threads = []
for worker_address in worker_addresses:
    t = RunProgramThread(worker_address, USER_ACCOUNT_ADDRESS)
    t.start()
    threads.append(t)

for t in threads:
    t.join(timeout=10)

final_xdr = ""


def merge_envelops(xdr1, xdr2):
    imported_xdr1 = TxEnv.TransactionEnvelope.from_xdr(xdr1)
    imported_xdr2 = TxEnv.TransactionEnvelope.from_xdr(xdr2)

    if imported_xdr1.hash_meta() != imported_xdr2.hash_meta():
        raise Exception("cannot merge envelops, because envelops is equals with each other")

    for sign in imported_xdr2.signatures:
        imported_xdr1.signatures.append(sign)

    envelop1 = Te(tx=Tx.Transaction.from_xdr_object(imported_xdr1.to_xdr_object()),
                  signatures=imported_xdr1.signatures, network_id=imported_xdr1.network_id)

    return envelop1.xdr()


def sign_envelop(xdr, secret_key):
    imported_xdr = TxEnv.TransactionEnvelope.from_xdr(xdr)

    envelop = Te(tx=imported_xdr, signatures=imported_xdr.signatures, network_id=NETWORK_PASSPHRASE)

    envelop.sign(Keypair.from_seed(secret_key))

    return envelop.xdr()


signer_count = 0

for res in workers_results:
    if res['result'].ok:
        worker_response = res['result'].content.decode()
        print("worker did the job and got result back: " + worker_response)

        if final_xdr == "":
            final_xdr = json.loads(worker_response)['xdr']
            signer_count += 1
            continue

        try:
            merge_envelops(final_xdr, json.loads(worker_response)['xdr'])
        except Exception as e:
            print(e)
            continue

        imported_xdr = TxEnv.TransactionEnvelope.from_xdr(json.loads(worker_response)['xdr'])

        keypair = Keypair.from_address(worker_address['public_key'])
        envelop = Te(tx=Tx.Transaction.from_xdr_object(imported_xdr.to_xdr_object()),
                     signatures=imported_xdr.signatures, network_id=NETWORK_PASSPHRASE)

        signer_count += 1
    else:
        print("worker got error: " + res['result'].content.decode())

if signer_count >= smart_account_info['thresholds']['med_threshold']:
    final_xdr = sign_envelop(final_xdr, USER_SECRET_KEY)
    final_envelop = Te(tx=TxEnv.TransactionEnvelope.from_xdr(final_xdr))
    submit_transaction_result = horizon.submit(final_envelop.xdr())
    print("transaction submitted to network")
else:
    print("couldn't collect enough sign for changing state")
