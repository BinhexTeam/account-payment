import logging

import requests

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PlaidController(http.Controller):
    @http.route(
        "/payment/plaid/get_link_token",
        type="json",
        auth="public",
        methods=["POST"],
        cors="*",
    )
    def get_link_token(self, provider_id=None, transaction_id=None):
        """Genera un link_token de Plaid para Transfer."""
        if not provider_id:
            return {"error": "provider_id not specified"}
        if not transaction_id:
            return {"error": "transaction_id not specified"}

        transaction = (
            request.env["payment.transaction"].sudo().browse(int(transaction_id))
        )
        if not transaction or not transaction.provider_id:
            return {"error": "No valid payment transaction."}

        provider = transaction.provider_id
        if provider.code != "plaid_manual":
            return {"error": "Not using 'plaid_manual' as payment provider."}

        plaid_env = provider.plaid_env or "sandbox"
        plaid_url = {
            "sandbox": "https://sandbox.plaid.com",
            "development": "https://development.plaid.com",
            "production": "https://production.plaid.com",
        }.get(plaid_env, "https://sandbox.plaid.com")

        payload = {
            "client_id": provider.plaid_client_id,
            "secret": provider.plaid_secret,
            "user": {"client_user_id": f"odoo_user_{request.session.uid}"},
            "client_name": "Odoo Shop",
            "products": ["transfer"],
            "country_codes": ["US"],
            "language": "en",
        }

        try:
            r = requests.post(
                f"{plaid_url}/link/token/create", json=payload, timeout=10
            )
            data = r.json()
            if r.status_code != 200 or "link_token" not in data:
                return {
                    "error": data.get("error_message", "Error generating link_token")
                }
            return data
        except Exception as e:
            return {"error": f"Error requesting link_token from Plaid: {str(e)}"}

    @http.route(
        "/payment/plaid/submit", type="json", auth="public", methods=["POST"], cors="*"
    )
    def plaid_submit(self, **kwargs):
        """
        Recibe public_token y account_id tras la autenticación en Plaid Link.
        1) Exchange public_token -> access_token
        2) Crear Transfer Authorization
        3) Crear Transfer
        4) Confirmar la transacción en Odoo
        """
        public_token = kwargs.get("public_token")
        account_id = kwargs.get("account_id")
        provider_id = kwargs.get("provider_id")
        transaction_id = kwargs.get("transaction_id")

        if not (public_token and account_id and provider_id and transaction_id):
            return {"error": "Missing parameters."}

        transaction = (
            request.env["payment.transaction"].sudo().browse(int(transaction_id))
        )
        if not transaction or transaction.provider_id.id != int(provider_id):
            return {"error": "Invalid transaction or provider mismatch."}

        provider = transaction.provider_id

        plaid_env = provider.plaid_env or "sandbox"
        plaid_url = {
            "sandbox": "https://sandbox.plaid.com",
            "development": "https://development.plaid.com",
            "production": "https://production.plaid.com",
        }.get(plaid_env, "https://sandbox.plaid.com")

        try:
            exchange_res = requests.post(
                f"{plaid_url}/item/public_token/exchange",
                json={
                    "client_id": provider.plaid_client_id,
                    "secret": provider.plaid_secret,
                    "public_token": public_token,
                },
                timeout=10,
            )
            exchange_data = exchange_res.json()
        except Exception as e:
            transaction._set_error("Error communicating with Plaid (token exchange).")
            return {"error": f"Error exchanging public token: {str(e)}"}

        if exchange_res.status_code != 200 or "access_token" not in exchange_data:
            err_msg = (
                exchange_data.get("error_message")
                or exchange_data.get("error")
                or "Unknown error"
            )
            transaction._set_error(f"Failure in public_token exchange: {err_msg}")
            return {"error": f"Failed to exchange public_token: {err_msg}"}

        access_token = exchange_data["access_token"]

        amount_str = f"{transaction.amount:.2f}"
        auth_payload = {
            "client_id": provider.plaid_client_id,
            "secret": provider.plaid_secret,
            "access_token": access_token,
            "account_id": account_id,
            "type": "debit",
            "amount": amount_str,
            "ach_class": "ppd",
            "network": "ach",
            "user": {
                "legal_name": transaction.partner_id.name or "Unknown",
                "email_address": transaction.partner_id.email or "",
            },
        }
        try:
            auth_res = requests.post(
                f"{plaid_url}/transfer/authorization/create",
                json=auth_payload,
                timeout=10,
            )
            auth_data = auth_res.json()
        except Exception as e:
            transaction._set_error("Error creating authorization in Plaid.")
            return {"error": f"Error in transfer/authorization/create: {str(e)}"}

        if auth_res.status_code != 200 or not auth_data.get("authorization"):
            err_msg = auth_data.get("error_message") or "Unknown error in authorization"
            transaction._set_error(f"Transfer failure (authorization): {err_msg}")
            return {"error": err_msg}

        if auth_data["authorization"].get("decision") == "declined":
            transaction._set_error("Transaction declined by Plaid.")
            return {"result": "error", "redirect_url": "/payment/status"}

        authorization_id = auth_data["authorization"]["id"]

        web_base_url = (
            request.env["ir.config_parameter"].sudo().get_param("web.base.url")
        )
        transfer_payload = {
            "client_id": provider.plaid_client_id,
            "secret": provider.plaid_secret,
            "access_token": access_token,
            "account_id": account_id,
            "authorization_id": authorization_id,
            "description": transaction.reference[:15],
            "metadata": {"webhook": f"{web_base_url}/payment/plaid/webhook"},
        }
        try:
            transfer_res = requests.post(
                f"{plaid_url}/transfer/create", json=transfer_payload, timeout=10
            )
            transfer_data = transfer_res.json()
        except Exception as e:
            transaction._set_error("Error creating transfer in Plaid.")
            return {"error": f"Error in transfer/create: {str(e)}"}

        if transfer_res.status_code != 200 or not transfer_data.get("transfer"):
            err_msg = (
                transfer_data.get("error_message")
                or "Unknown error while creating transfer"
            )
            transaction._set_error(f"Failed to create transfer: {err_msg}")
            return {"error": err_msg}

        transfer_id = transfer_data["transfer"]["id"]
        transaction.provider_reference = transfer_id

        transaction._set_done()
        transaction._create_payment()

        return {"result": "success", "redirect_url": "/payment/status"}

    @http.route("/payment/plaid/webhook", type="json", auth="public", csrf=False)
    def plaid_webhook(self, **data):
        data = request.httprequest.json
        webhook_type = data.get("webhook_type")
        webhook_code = data.get("webhook_code")

        if webhook_type == "TRANSFER" and webhook_code == "TRANSFER_EVENTS_UPDATE":
            provider = (
                request.env["payment.provider"]
                .sudo()
                .search([("code", "=", "plaid_manual")], limit=1)
            )
            plaid_url = f"https://{provider.plaid_env}.plaid.com"

            events_res = requests.post(
                f"{plaid_url}/transfer/event/list",
                json={
                    "client_id": provider.plaid_client_id,
                    "secret": provider.plaid_secret,
                    "count": 10,
                },
                timeout=10,
            )

            events_res.raise_for_status()
            events_data = events_res.json()

            for event in events_data.get("transfer_events", []):
                transfer_id = event.get("transfer_id")
                event_type = event.get("event_type")

                if event_type == "posted":
                    transaction = (
                        request.env["payment.transaction"]
                        .sudo()
                        .search(
                            [
                                ("provider_reference", "=", transfer_id),
                                ("state", "!=", "done"),
                            ],
                            limit=1,
                        )
                    )

                    if transaction:
                        transfer_res = requests.post(
                            f"{plaid_url}/transfer/get",
                            json={
                                "client_id": provider.plaid_client_id,
                                "secret": provider.plaid_secret,
                                "transfer_id": transfer_id,
                            },
                            timeout=10,
                        )
                        transfer_res.raise_for_status()
                        transfer_data = transfer_res.json()

                        if transfer_data["transfer"]["status"] == "posted":
                            transaction._set_done()
                            transaction._create_payment()

                            sale_order = (
                                request.env["sale.order"]
                                .sudo()
                                .search([("name", "=", transaction.reference)], limit=1)
                            )
                            if sale_order and sale_order.state != "sale":
                                sale_order.sudo().action_confirm()

            return {"status": "processed"}

        return {"status": "ignored", "reason": "Not a valid ACH transfer webhook"}
