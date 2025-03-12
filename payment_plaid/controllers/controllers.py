import json
import requests
from odoo import http
from odoo.http import request
import logging
_logger = logging.getLogger(__name__)

from odoo.exceptions import ValidationError

class PlaidController(http.Controller):

    @http.route('/payment/plaid/get_link_token', type='json', auth='public', methods=['POST'], cors="*")
    def get_link_token(self, provider_id=None):
        """Genera un link_token de Plaid para Transfer."""
        if not provider_id:
            return {'error': 'provider_id not specified'}

        provider = request.env['payment.provider'].sudo().browse(
            int(provider_id))
        if not provider:
            return {'error': 'Payment provider (Plaid) not found.'}

        plaid_env = provider.plaid_env or 'sandbox'
        plaid_url = {
            'sandbox': 'https://sandbox.plaid.com',
            'development': 'https://development.plaid.com',
            'production': 'https://production.plaid.com',
        }.get(plaid_env, 'https://sandbox.plaid.com')

        # IMPORTANTE: products=["transfer"] para crear un Link Token de Transfer
        payload = {
            "client_id": provider.plaid_client_id,
            "secret": provider.plaid_secret,
            "user": {
                # ID único para identificar al usuario final dentro de Plaid
                "client_user_id": f"odoo_user_{request.session.uid}"
            },
            "client_name": "Odoo Shop",
            "products": ["transfer"],   # <--- Asegúrate de que sea 'transfer'
            "country_codes": ["US"],
            "language": "en",
        }

        try:
            r = requests.post(
                f"{plaid_url}/link/token/create", json=payload, timeout=10)
            data = r.json()
            if r.status_code != 200 or 'link_token' not in data:
                return {'error': data.get('error_message', 'Error generating link_token')}
            return data
        except Exception as e:
            return {'error': f"Error al solicitar link_token a Plaid: {str(e)}"}

    @http.route('/payment/plaid/submit', type='json', auth='public', methods=['POST'], cors="*")
    def plaid_submit(self, **kwargs):
        """
        Recibe public_token y account_id tras la autenticación en Plaid Link,
        y crea la Transfer en Plaid:
          1) Exchange public_token -> access_token
          2) Crear Transfer Authorization
          3) Crear Transfer
          4) Marcar transacción en Odoo como pagada (o pendiente).
        """
        public_token = kwargs.get('public_token')
        account_id = kwargs.get('account_id')
        provider_id = kwargs.get('provider_id')

        if not public_token or not account_id or not provider_id:
            return {'error': 'Faltan datos necesarios (public_token/account_id/provider_id).'}

        provider = request.env['payment.provider'].sudo().browse(
            int(provider_id))
        if not provider:
            return {'error': 'Payment provider Plaid not found.'}

        # Obtenemos el sale_order (carrito) para calcular monto y crear transacción
        website = request.env['website'].get_current_website()
        sale_order = website.sale_get_order()
        if not sale_order:
            return {'error': 'There is no active sales order (sale_order) to process.'}

        PaymentTransaction = request.env['payment.transaction'].sudo()
        transaction = PaymentTransaction.search(
            [('reference', '=', sale_order.name)], limit=1)

        if not transaction:
            # Crear transacción si no existe
            transaction_vals = {
                'amount': sale_order.amount_total,
                'currency_id': sale_order.currency_id.id,
                'provider_id': provider.id,
                'operation': 'online_redirect',
                'partner_id': sale_order.partner_id.id,
                'reference': sale_order.name,
            }
            transaction = PaymentTransaction.create(transaction_vals)
        else:
            # Actualizar la transacción existente si fuera necesario
            transaction.write({
                'amount': sale_order.amount_total,
                'currency_id': sale_order.currency_id.id
            })

        # --- Paso 1) Intercambio del public_token -> access_token ---
        plaid_env = provider.plaid_env or 'sandbox'
        plaid_url = {
            'sandbox': 'https://sandbox.plaid.com',
            'development': 'https://development.plaid.com',
            'production': 'https://production.plaid.com',
        }.get(plaid_env, 'https://sandbox.plaid.com')

        try:
            exchange_res = requests.post(
                f"{plaid_url}/item/public_token/exchange",
                json={
                    "client_id": provider.plaid_client_id,
                    "secret": provider.plaid_secret,
                    "public_token": public_token
                },
                timeout=10
            )
            exchange_data = exchange_res.json()
        except Exception as e:
            transaction._set_error(
                "Error communicating with Plaid (token exchange).")
            return {'error': f"Error exchanging public token: {str(e)}"}

        if exchange_res.status_code != 200 or 'access_token' not in exchange_data:
            err_msg = exchange_data.get('error_message') or exchange_data.get(
                'error') or 'Unknown error'
            transaction._set_error(
                f"Failure in public_token exchange: {err_msg}")
            return {'error': f"Failed to exchange public_token: {err_msg}"}

        access_token = exchange_data['access_token']

        # --- Paso 2) Crear la autorización de la Transfer ---
        # Documentación: https://plaid.com/docs/api/transfer/#transferauthorizationcreate
        amount_str = "{:.2f}".format(sale_order.amount_total)
        auth_payload = {
            "client_id": provider.plaid_client_id,
            "secret": provider.plaid_secret,
            "access_token": access_token,
            "account_id": account_id,
            "type": "debit",
            "amount": amount_str,  # 2 decimales
            "ach_class": "ppd",
            "network": "ach", 
            "user": {
                "legal_name": sale_order.partner_id.name,
                "email_address": sale_order.partner_id.email,
            }
        }
        try:
            auth_res = requests.post(f"{plaid_url}/transfer/authorization/create",
                                     json=auth_payload,
                                     timeout=10)
            auth_data = auth_res.json()
        except Exception as e:
            transaction._set_error("Error creating authorization in Plaid.")
            return {'error': f"Error in transfer/authorization/create: {str(e)}"}

        if auth_res.status_code != 200 or not auth_data.get('authorization'):
            err_msg = auth_data.get(
                'error_message') or 'Unknown error in authorization'
            transaction._set_error(
                f"Transfer failure (authorization): {err_msg}")
            return {'error': err_msg}

        authorization_id = auth_data['authorization']['id']

        # --- Paso 3) Crear la Transfer con la autorización ---
        # https://plaid.com/docs/api/transfer/#transfercreate
        web_base_url = request.env["ir.config_parameter"].sudo().get_param("web.base.url")
        transfer_payload = {
            "client_id": provider.plaid_client_id,
            "secret": provider.plaid_secret,
            "access_token": access_token,
            "account_id": account_id,
            "authorization_id": authorization_id,           
            "description": sale_order.name,    # máx 15 chars            
            "metadata": {
                "webhook": "{}/payment/plaid/webhook".format(web_base_url)
            }
        }
        try:
            transfer_res = requests.post(
                f"{plaid_url}/transfer/create", json=transfer_payload, timeout=10)
            transfer_data = transfer_res.json()
        except Exception as e:
            transaction._set_error("Error creating transfer in Plaid.")
            return {'error': f"Error in transfer/create: {str(e)}"}

        if transfer_res.status_code != 200 or not transfer_data.get('transfer'):
            err_msg = transfer_data.get(
                'error_message') or 'Unknown error while creating transfer'
            transaction._set_error(f"Failed to create transfer: {err_msg}")
            return {'error': err_msg}

        transfer_id = transfer_data['transfer']['id']

        # Guardar en la transacción
        transaction.provider_reference = transfer_id 
        
        # Vincula la transacción al pedido y confirma el pedido correctamente
        sale_order.write({
            'transaction_ids': [(4, transaction.id)],
        })
        transaction._set_done()
        transaction._create_payment()       
        sale_order.sudo().action_confirm()

        # Limpieza de la sesión para que no siga existiendo el carrito
        request.session['sale_last_order_id'] = sale_order.id
        request.session['sale_order_id'] = False

        # Redireccionamos al usuario a la confirmación nativa de Odoo
        return {
            'result': 'success',
            'redirect_url': '/payment/status'
        }

    @http.route('/payment/plaid/webhook', type='json', auth='public', csrf=False)
    def plaid_webhook(self, **data):
        data = request.httprequest.json
        webhook_type = data.get('webhook_type')
        webhook_code = data.get('webhook_code')

        if webhook_type == 'TRANSFER' and webhook_code == 'TRANSFER_EVENTS_UPDATE':
            provider = request.env['payment.provider'].sudo().search([('code', '=', 'plaid_manual')], limit=1)
            plaid_url = f"https://{provider.plaid_env}.plaid.com"

            # Paso 1: Consultar eventos recientes para saber cuál transferencia cambió.
            events_res = requests.post(
                f"{plaid_url}/transfer/event/list",
                json={
                    "client_id": provider.plaid_client_id,
                    "secret": provider.plaid_secret,
                    "count": 10,  # últimos 10 eventos (ajusta según necesidad)
                },
                timeout=10
            )

            events_res.raise_for_status()
            events_data = events_res.json()

            for event in events_data.get('transfer_events', []):
                transfer_id = event.get('transfer_id')
                event_type = event.get('event_type')

                # Solo procesa eventos recientes relevantes (ejemplo: "posted")
                if event_type == 'posted':
                    transaction = request.env['payment.transaction'].sudo().search([
                        ('provider_reference', '=', transfer_id),
                        ('state', '!=', 'done')
                    ], limit=1)

                    if transaction:
                        # Verifica estado actual de la transferencia
                        transfer_res = requests.post(
                            f"{plaid_url}/transfer/get",
                            json={
                                "client_id": provider.plaid_client_id,
                                "secret": provider.plaid_secret,
                                "transfer_id": transfer_id
                            },
                            timeout=10
                        )
                        transfer_res.raise_for_status()
                        transfer_data = transfer_res.json()

                        if transfer_data['transfer']['status'] == 'posted':
                            transaction._set_done()
                            transaction._create_payment()

                            sale_order = request.env['sale.order'].sudo().search([
                                ('name', '=', transaction.reference)
                            ], limit=1)
                            if sale_order and sale_order.state != 'sale':
                                sale_order.sudo().action_confirm()

            return {'status': 'processed'}
        
        return {'status': 'ignored', 'reason': 'Not a valid ACH transfer webhook'}


    