"""Payout seam: how a filled bounty jar reaches the builder who won it.

Nothing calls this automatically. A person decides who won, then calls
provider.pay(...). Supervised, same as the curator flow.
"""

from __future__ import annotations

from typing import Protocol

from hackheat import paypal


class PayoutProvider(Protocol):
    name: str

    def pay(self, opportunity_id: str, amount_usd: float, recipient: str) -> dict:
        """Send amount_usd to recipient for the bounty on opportunity_id."""
        ...


class PayPalPayout:
    """PayPal Payouts API (sandbox). recipient is the winner's PayPal email."""

    name = "paypal"

    def pay(self, opportunity_id: str, amount_usd: float, recipient: str) -> dict:
        if "@" not in recipient:
            raise ValueError("PayPal payouts need the recipient's PayPal email.")
        batch_id = f"hackheat-{opportunity_id}"[:127]
        return paypal.payout(recipient, amount_usd, f"Hack Heat bounty for {opportunity_id}", batch_id)


class NearIntentsPayout:
    """Placeholder for the NEAR hackathon (closes 15 Nov 2026).

    Plan: quote the USD amount as a NEAR Intents swap into whatever asset the
    winner asks for, have the solver network settle it to their NEAR account
    (recipient = account id such as alice.near), and return the intent hash.
    Funding comes from the jar's PayPal balance, so this needs an off-ramp or a
    treasury account first. Not built in v0.
    """

    name = "near-intents"

    def pay(self, opportunity_id: str, amount_usd: float, recipient: str) -> dict:
        raise NotImplementedError("NEAR Intents payout is not built yet. See the class docstring.")


PROVIDERS: dict[str, PayoutProvider] = {"paypal": PayPalPayout(), "near-intents": NearIntentsPayout()}
