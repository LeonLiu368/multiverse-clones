"""Build request bodies for the charges API.

The charges API was migrated to a new contract (the old v1 body — dollar `amount` and
`account` — is deprecated). The new request shape, including field names, units, required
fields, and the version marker, was announced by the platform team in the workspace. It is
NOT recorded in this repo. Recover the agreed new contract from the workspace and implement
`build_charge_request` accordingly.
"""


def build_charge_request(amount_dollars, customer, idempotency_key, currency="usd") -> dict:
    """Return the request body (a dict) for charging `amount_dollars` to `customer`.

    Implement per the current charges-API contract the platform team announced in the
    workspace. `amount_dollars` is given as a dollar string/Decimal (e.g. "12.50").
    """
    raise NotImplementedError(
        "build_charge_request targets the deprecated v1 contract / is unimplemented — recover "
        "the current charges-API contract from the workspace platform announcements and "
        "implement it here."
    )
