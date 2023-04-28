from beaker import *
from pyteal import *


class FitnessStates:
    ### global ###
    challenger_addr = GlobalStateValue(
        stack_type=TealType.bytes, static=True, descr="Address of the challenger"
    )
    challenger_stake = GlobalStateValue(
        stack_type=TealType.uint64, static=True, descr="Stake amount of the challenger"
    )

    supporter_stake = GlobalStateValue(
        stack_type=TealType.uint64, static=True, descr="Stake amount of the supporter"
    )

    total_stake = GlobalStateValue(
        stack_type=TealType.uint64, descr="Stake amount of the supporter"
    )

    num_supporter = GlobalStateValue(
        stack_type=TealType.uint64, default=Int(0), descr="Number of supporter"
    )

    list_of_supporters = ReservedGlobalStateValue(
        stack_type=TealType.bytes, max_keys=10, descr="List of supporter addresses"
    )

    # list_of_supporters = GlobalStateBlob(keys=2, descr="List of supporter addresses")

    challenge_started = GlobalStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Check if challenge is in progress",
    )

    ### local ###

    staked = LocalStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Check if the account staked. false: Int(0), true: Int(1)",
    )

    role = LocalStateValue(
        stack_type=TealType.uint64,
        descr="Supporter: Int(0), Challenger: Int(1)",
    )

    # # - stake_amount
    # stake_amount = LocalStateValue(
    #     stack_type=TealType.uint64,
    #     default=Int(0),
    #     descr="Check if the account staked. false: Int(0), true: Int(1)"
    # )


app = Application("fitness challenge app", state=FitnessStates())


# create(challenger stake)
# - initialize global state
# - auto calculate supporter stake to be 1/10th (call internal calc method)
# - set challenger address
@app.create
def app_create(stake_amt: abi.Uint64) -> Expr:
    return Seq(
        app.initialize_global_state(),
        app.state.challenger_addr.set(Txn.sender()),
        app.state.challenger_stake.set(stake_amt.get()),
        app.state.supporter_stake.set(calculate_support_stake(stake_amt)),
    )


@Subroutine(return_type=TealType.uint64)
def calculate_support_stake(stake: abi.Uint64) -> Expr:
    return stake.get() / Int(10)


# optin(role)
# - local state initialize
# - if challenger,
#     check if address = challenger addr
#     role set to 1
# - if supporter
#     role set to 0


@app.external
def read_challenger_addr(*, output: abi.Address) -> Expr:
    return output.set(app.state.challenger_addr)


@app.opt_in
def optin_role(addr_role: abi.Uint8, k: abi.Uint8, *, output: abi.String) -> Expr:
    return Seq(
        Assert(app.state.challenge_started == Int(0)),
        app.initialize_local_state(),
        If(addr_role.get() == Int(1))
        .Then(
            Seq(
                Assert(Txn.sender() == app.state.challenger_addr),
                app.state.role[Txn.sender()].set(Int(1)),
            )
        )
        .ElseIf(addr_role.get() == Int(0))
        .Then(
            Seq(
                Assert(Txn.sender() != app.state.challenger_addr),
                app.state.role[Txn.sender()].set(Int(0)),
                app.state.list_of_supporters[k].set(Txn.sender()),
                app.state.num_supporter.set(app.state.num_supporter + Int(1)),
            )
        )
        .Else(output.set("Test!")),
    )


# @app.external
# def read_supporter(*, output: abi.Address) -> Expr:
#     return output.set(
#         app.state.list_of_supporters.read(
#             Int(0), app.state.list_of_supporters.blob.max_bytes - Int(1)
#         )
#     )


# @app.opt_in
# def optin_role_test() -> Expr:
#     return Seq(
#         Assert(app.state.challenge_started == Int(0)),
#         # Assert(Txn.sender() == app.state.challenger_addr),
#         # app.state.role[Txn.sender()].set(Int(1)),
#         app.initialize_local_state(),
#     )


# pay
# - check if account staked already
# - check if challenger or supporter
# - check amount is stake amount
# - set staked to true
@app.external(authorize=Authorize.opted_in())
def deposit_stake(pay: abi.PaymentTransaction) -> Expr:
    return Seq(
        Assert(app.state.staked[Txn.sender()] == Int(0)),
        If(app.state.role[Txn.sender()] == Int(1))
        .Then(
            Assert(pay.get().amount() == app.state.challenger_stake),
            app.state.total_stake.set(app.state.total_stake + pay.get().amount()),
            app.state.staked[Txn.sender()].set(Int(1)),
        )
        .ElseIf(app.state.role[Txn.sender()] == Int(0))
        .Then(
            Assert(pay.get().amount() == app.state.supporter_stake),
            app.state.total_stake.set(app.state.total_stake + pay.get().amount()),
            app.state.staked[Txn.sender()].set(Int(1)),
        )
        .Else(Reject()),
    )


# start_challenge()
# - check challenger staked = true
# - check supporter number > 0
@app.external(authorize=Authorize.only_creator())
def start_challenge() -> Expr:
    return Seq(
        Assert(app.state.staked[Txn.sender()] == Int(1)),
        Assert(app.state.num_supporter > Int(0)),
        app.state.challenge_started.set(Int(1)),
    )


# - no more supporters can join
# - supporters, challengers cannot pull out funds


# end_challenge(success / fail )
# - if success
#     - send all funds to challenger
# - if fail
#     - divide total fund by supporter amount and send payment txn to supporters
#         - for loop
@app.external(authorize=Authorize.only_creator())
def end_challenge(result: abi.Uint8) -> Expr:
    i = ScratchVar(TealType.uint64)
    supporter_reward = ScratchVar(TealType.uint64)

    return Seq(
        If(result.get() == Int(1))
        .Then(claim_funds(app.state.challenger_addr, app.state.total_stake))
        .ElseIf(result.get() == Int(0))
        .Then(
            Seq(
                supporter_reward.store(app.state.total_stake / app.state.num_supporter),
                For(
                    i.store(Int(0)),
                    i.load() < app.state.num_supporter,
                    i.store(i.load() + Int(1)),
                ).Do(
                    claim_funds(
                        app.state.list_of_supporters[i.load()],
                        supporter_reward.load(),  # can only take abi type
                    )
                ),
            )
        )
        .Else(Reject()),
        app.state.total_stake.set(Int(0)),
        app.state.challenge_started.set(Int(0)),
    )


@Subroutine(return_type=TealType.none)
def claim_funds(receiver: Expr, amount: Expr) -> Expr:
    return InnerTxnBuilder.Execute(
        {
            TxnField.type_enum: TxnType.Payment,
            TxnField.receiver: receiver,
            TxnField.amount: amount,
            TxnField.fee: Int(0),  # cover fee with outer txn
        }
    )


# delete
# - check if total stake = 0
# - check if challenged ended
@app.delete(authorize=Authorize.only_creator())
def delete() -> Expr:
    return Seq(
        Assert(app.state.challenge_started == Int(0)),
        Assert(app.state.total_stake == Int(0)),
        Approve(),
    )


if __name__ == "__main__":
    app.build().export("./artifacts")
