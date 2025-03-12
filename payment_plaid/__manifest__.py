{
    'name': 'Plaid ACH Payment Integration',
    'summary': 'Plaid integration (ACH via manual transfer) as an eCommerce payment method',
    'description': 'Add payment methods that use Plaid to link bank accounts, with the option to collect ACH payments via manually transfer.',
    'author': 'Ing. Carlos R. Rodriguez',
    'website': 'https://github.com/BinhexTeam/account-payment',
    'category': 'Accounting/Payment Providers',
    'version': '16.0.1.0',
    'license': 'LGPL-3',
    'depends': ['payment', 'website_sale'],
    'data': [
        # Extensión de la vista de configuraciones de pago
        'views/payment_views.xml',
        # Plantillas QWeb para las formas de pago en el checkout
        'views/payment_plaid_templates.xml',
        # Datos de los proveedores de pago Plaid (Stripe ACH y Transferencia)
        'data/payment_provider_data.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'assets': {
        'web.assets_frontend': [
            'payment_plaid/static/src/js/**/*',
        ],
    },
    'installable': True,
}
