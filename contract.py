from beaker import GlobalStateValue, LocalStateValue, Application, Authorize
from pyteal import (
    TealType,
    abi,
    Expr,
    Seq,
    Txn,
    Assert,
    Int,
    If,
    Reject,
    Approve,
    Subroutine,
    InnerTxnBuilder,
    TxnField,
    TxnType,
)


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

    challenge_started = GlobalStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Check if challenge is in progress. Int(0): not started, Int(1): in progress, Int(2): finished",
    )

    challenge_result = GlobalStateValue(
        stack_type=TealType.uint64,
        descr="Int(1) if challenger successful, Int(0) if challenger fails.",
    )

    supporter_reward = GlobalStateValue(
        stack_type=TealType.uint64,
        static=True,
        descr="How much each supporter should get if challenger fails.",
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

    claimed = LocalStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Check if the account claimed reward. false: Int(0), true: Int(1)",
    )


app = Application("fitness challenge app", state=FitnessStates())


@app.create
def app_create(stake_amt: abi.Uint64) -> Expr:
    return Seq(
        app.initialize_global_state(),
        app.state.challenger_addr.set(Txn.sender()),
        app.state.challenger_stake.set(stake_amt.get()),
        app.state.supporter_stake.set(calculate_support_stake(stake_amt)),
    )


@app.external
def read_challenger_addr(*, output: abi.Address) -> Expr:
    return output.set(app.state.challenger_addr)


@app.opt_in
def optin_role(addr_role: abi.Uint8, *, output: abi.String) -> Expr:
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
                app.state.num_supporter.set(app.state.num_supporter + Int(1)),
            )
        )
        .Else(output.set("Test!")),
    )


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


@app.external(authorize=Authorize.only_creator())
def start_challenge() -> Expr:
    return Seq(
        Assert(app.state.staked[Txn.sender()] == Int(1)),
        Assert(app.state.num_supporter > Int(0)),
        app.state.supporter_reward.set(app.state.total_stake / app.state.num_supporter),
        app.state.challenge_started.set(Int(1)),
    )


@app.external(authorize=Authorize.only_creator())
def end_challenge(result: abi.Uint8) -> Expr:
    return Seq(
        app.state.challenge_result.set(result.get()),
        app.state.challenge_started.set(Int(2)),
        Approve(),
    )


@app.external(authorize=Authorize.opted_in())
def claim_funds() -> Expr:
    return Seq(
        Assert(app.state.claimed[Txn.sender()] == Int(0)),
        Assert(app.state.challenge_started == Int(2)),
        Assert(app.state.staked[Txn.sender()] == Int(1)),
        Assert(app.state.total_stake > Int(0)),
        If(app.state.challenge_result == Int(1))
        .Then(
            Seq(
                Assert(Txn.sender() == app.state.challenger_addr),
                Assert(app.state.role[Txn.sender()] == Int(1)),
                send_payment(Txn.sender(), app.state.total_stake),
                app.state.claimed[Txn.sender()].set(Int(1)),
                app.state.staked[Txn.sender()].set(Int(0)),
                app.state.total_stake.set(Int(0)),
            )
        )
        .ElseIf(app.state.challenge_result == Int(0))
        .Then(
            Seq(
                Assert(Txn.sender() != app.state.challenger_addr),
                Assert(app.state.role[Txn.sender()] == Int(0)),
                send_payment(Txn.sender(), app.state.supporter_reward),
                app.state.claimed[Txn.sender()].set(Int(1)),
                app.state.staked[Txn.sender()].set(Int(0)),
                app.state.total_stake.set(
                    app.state.total_stake - app.state.supporter_reward
                ),
            )
        )
        .Else(Reject()),
    )


@app.delete(authorize=Authorize.only_creator())
def delete() -> Expr:
    return Seq(
        Assert(app.state.challenge_started != Int(1)),
        Assert(app.state.total_stake == Int(0)),
        Approve(),
    )


### Internal Subroutines ###


@Subroutine(return_type=TealType.uint64)
def calculate_support_stake(stake: abi.Uint64) -> Expr:
    return stake.get() / Int(2)


@Subroutine(return_type=TealType.none)
def send_payment(receiver: Expr, amount: Expr) -> Expr:
    return InnerTxnBuilder.Execute(
        {
            TxnField.type_enum: TxnType.Payment,
            TxnField.receiver: receiver,
            TxnField.amount: amount,
            TxnField.fee: Int(0),  # cover fee with outer txn
        }
    )
