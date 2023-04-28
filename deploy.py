from typing import Any, Dict

from algosdk import transaction
from algosdk.atomic_transaction_composer import (
    TransactionWithSigner,
)
from beaker import client, sandbox, consts

from contract import app, deposit_stake, end_challenge, start_challenge, claim_funds

app.build().export("./artifacts")


def demo(result: str, stake_amount: int) -> None:
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

    challenger_client.opt_in(addr_role=1)

    return_value = challenger_client.get_local_state()
    print(f"Challenger local state: {return_value}")

    supporter1_client = challenger_client.prepare(signer=supporter1.signer)
    supporter1_client.opt_in(addr_role=0)

    return_value = supporter1_client.get_local_state()
    print(f"Supporter1 local state: {return_value}")

    supporter2_client = challenger_client.prepare(signer=supporter2.signer)
    supporter2_client.opt_in(addr_role=0)

    return_value = supporter2_client.get_local_state()
    print(f"Supporter2 local state: {return_value}")

    print(f"global state: {challenger_client.get_global_state()}")

    ### Challenger stake ###
    sp = algod_client.suggested_params()
    ptxn = TransactionWithSigner(
        txn=transaction.PaymentTxn(challenger.address, sp, app_addr, stake_amount),
        signer=challenger.signer,
    )

    challenger_client.call(deposit_stake, pay=ptxn)
    print(f"global state: {challenger_client.get_global_state()}")
    print(f"Challenger local state: {challenger_client.get_local_state()}")

    ### Supporter 1 stake ###
    sp = algod_client.suggested_params()
    ptxn = TransactionWithSigner(
        txn=transaction.PaymentTxn(supporter1.address, sp, app_addr, stake_amount // 2),
        signer=supporter1.signer,
    )

    supporter1_client.call(deposit_stake, pay=ptxn)
    print(f"global state: {supporter1_client.get_global_state()}")
    print(f"supporter1 local state: {supporter1_client.get_local_state()}")

    ### Supporter 2 stake ###
    sp = algod_client.suggested_params()
    ptxn = TransactionWithSigner(
        txn=transaction.PaymentTxn(supporter2.address, sp, app_addr, stake_amount // 2),
        signer=supporter2.signer,
    )
    supporter2_client.call(deposit_stake, pay=ptxn)
    print(f"global state: {supporter1_client.get_global_state()}")
    print(f"supporter2 local state: {supporter1_client.get_local_state()}")

    ### Start Challenge ###
    challenger_client.call(start_challenge)
    print("Challenge Started!")

    if result == "success":
        challenge_acct_info: Dict[str, Any] = algod_client.account_info(
            challenger.address
        )
        print(f"Account balance: {challenge_acct_info.get('amount')} microAlgos")

        challenger_client.call(method=end_challenge, result=True, suggested_params=sp)
        print(f"global state: {challenger_client.get_global_state()}")
        sp = algod_client.suggested_params()
        sp.fee = 2000
        challenger_client.call(method=claim_funds, suggested_params=sp)

        challenge_acct_info2: Dict[str, Any] = algod_client.account_info(
            challenger.address
        )

        earned = challenge_acct_info.get("amount") - challenge_acct_info2.get("amount")
        print(f"Challenger earned {earned} microAlgos")
    elif result == "fail":
        support1_acct_info: Dict[str, Any] = algod_client.account_info(
            supporter1.address
        )
        print(
            f"Supporter1 Account balance: {support1_acct_info.get('amount')} microAlgos"
        )

        challenger_client.call(end_challenge, result=False)

        sp = algod_client.suggested_params()
        sp.fee = 2000

        supporter1_client.call(claim_funds, suggested_params=sp)

        support1_acct_info2: Dict[str, Any] = algod_client.account_info(
            supporter1.address
        )
        print(
            f"Supporter1 Account balance: {support1_acct_info2.get('amount')} microAlgos"
        )

        support2_acct_info: Dict[str, Any] = algod_client.account_info(
            supporter1.address
        )
        print(
            f"Supporter2 Account balance: {support2_acct_info.get('amount')} microAlgos"
        )

        sp = algod_client.suggested_params()
        sp.fee = 2000

        supporter2_client.call(claim_funds, suggested_params=sp)

        support2_acct_info2: Dict[str, Any] = algod_client.account_info(
            supporter1.address
        )
        print(
            f"Supporter2 Account balance: {support2_acct_info2.get('amount')} microAlgos"
        )

    challenger_client.delete()
    print("app deleted!")


demo("success", consts.milli_algo * 1000)
