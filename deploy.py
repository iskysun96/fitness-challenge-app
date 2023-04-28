from typing import Any, Dict

from algosdk import transaction
from algosdk.atomic_transaction_composer import (
    TransactionWithSigner,
)
from beaker import client, sandbox, consts

from contract import app, deposit_stake, end_challenge, start_challenge

app.build().export("./artifacts")


def demo(result, stake_amount):
    accounts = sandbox.kmd.get_accounts()
    challenger = accounts[0]
    supporter1 = accounts[1]
    supporter2 = accounts[2]

    algod_client = sandbox.get_algod_client()

    challenger_client = client.ApplicationClient(
        client=algod_client,
        app=app,
        signer=challenger.signer,
    )

    app_id, app_addr, txid = challenger_client.create(stake_amt=stake_amount)
    print(f"global state: {challenger_client.get_global_state()}")

    challenger_client.fund(100000)

    challenger_client.opt_in(addr_role=1, k=0)

    return_value = challenger_client.get_local_state()
    print(f"Challenger local state: {return_value}")

    supporter1_client = challenger_client.prepare(signer=supporter1.signer)
    supporter1_client.opt_in(addr_role=0, k=0)

    return_value = supporter1_client.get_local_state()
    print(f"Supporter1 local state: {return_value}")

    supporter2_client = challenger_client.prepare(signer=supporter2.signer)
    supporter2_client.opt_in(addr_role=0, k=1)

    return_value = supporter2_client.get_local_state()
    print(f"Supporter2 local state: {return_value}")

    print(f"global state: {challenger_client.get_global_state()}")

    # return_val = challenger_client.call(read_supporter, index=0)
    # print(return_val.return_value)

    # return_val = challenger_client.call(read_supporter, index=1)
    # print(return_val.return_value)

    sp = algod_client.suggested_params()
    ptxn = TransactionWithSigner(
        txn=transaction.PaymentTxn(challenger.address, sp, app_addr, stake_amount),
        signer=challenger.signer,
    )

    challenger_client.call(deposit_stake, pay=ptxn)
    print(f"global state: {challenger_client.get_global_state()}")
    print(f"Challenger local state: {challenger_client.get_local_state()}")

    sp = algod_client.suggested_params()
    ptxn = TransactionWithSigner(
        txn=transaction.PaymentTxn(
            supporter1.address, sp, app_addr, stake_amount // 10
        ),
        signer=supporter1.signer,
    )

    supporter1_client.call(deposit_stake, pay=ptxn)
    print(f"global state: {supporter1_client.get_global_state()}")
    print(f"supporter1 local state: {supporter1_client.get_local_state()}")

    sp = algod_client.suggested_params()
    ptxn = TransactionWithSigner(
        txn=transaction.PaymentTxn(
            supporter2.address, sp, app_addr, stake_amount // 10
        ),
        signer=supporter2.signer,
    )
    supporter2_client.call(deposit_stake, pay=ptxn)
    print(f"global state: {supporter1_client.get_global_state()}")
    print(f"supporter2 local state: {supporter1_client.get_local_state()}")

    challenger_client.call(start_challenge)
    print("Challenge Started!")

    if result == "success":
        account_info: Dict[str, Any] = algod_client.account_info(challenger.address)
        print(f"Account balance: {account_info.get('amount')} microAlgos")

        sp = algod_client.suggested_params()
        sp.fee = 2000
        sp.flat_fee
        challenger_client.call(method=end_challenge, result=1, suggested_params=sp)

        account_info1: Dict[str, Any] = algod_client.account_info(challenger.address)
        print(f"Account balance: {account_info1.get('amount')} microAlgos")
    elif result == "fail":
        account_info: Dict[str, Any] = algod_client.account_info(supporter1.address)
        print(f"Supporter1 Account balance: {account_info.get('amount')} microAlgos")

        sp = algod_client.suggested_params()
        sp.fee = 2000
        sp.flat_fee
        challenger_client.call(end_challenge, result=0)

        account_info1: Dict[str, Any] = algod_client.account_info(supporter1.address)
        print(f"Supporter1 Account balance: {account_info1.get('amount')} microAlgos")


demo("fail", consts.milli_algo * 5)
