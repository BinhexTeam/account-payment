# Mapping of transaction states to Tilopay payment statuses.
PAYMENT_STATUS_MAPPING = {
    'pending': ['pending auth'],
    'done': ['transaccion aprobada', 'transaction is approved'],
    'cancel': ['cancelled'],
    'error': ['330-la transaccion es invalida, por favor verifique los datos brindados e intente nuevamente','insufficient funds','invalid cvv','330-the transaction is invalid, please verify the data provided and try again'],
}
