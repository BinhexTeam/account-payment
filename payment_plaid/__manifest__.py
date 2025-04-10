{
    "name": "Plaid ACH Payment Integration ",
    "summary": "Plaid integration (ACH via manual transfer)",
    "author": "Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/account-payment",
    "category": "Accounting/Payment Providers",
    "version": "17.0.1.0.0",
    "license": "LGPL-3",
    "depends": ["payment", "website_sale"],
    "data": [
        "views/payment_views.xml",
        "views/payment_plaid_templates.xml",
        "data/payment_provider_data.xml",
    ],
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "assets": {
        "web.assets_frontend": [
            "payment_plaid/static/src/js/payment_form.js",
        ],
    },
    "installable": True,
}
