from django.core import signing

ADDRESS_SELECTION_SIGNING_SALT = "listings.address_selection"


def sign_address_selection(payload):
    return signing.dumps(payload, salt=ADDRESS_SELECTION_SIGNING_SALT, compress=True)


def unsign_address_selection(token, *, max_age):
    return signing.loads(token, salt=ADDRESS_SELECTION_SIGNING_SALT, max_age=max_age)
