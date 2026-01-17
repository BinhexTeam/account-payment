from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.payment_plaid.controllers.controllers import PlaidController

# Nombre del logger definido en el controlador, para silenciar en pruebas de errores
CONTROLLER_LOGGER = "odoo.addons.payment_plaid.controllers.controllers"


class DummyResponse:
    """Objeto de simulación de respuesta HTTP (requests.Response) con JSON."""

    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


@tagged("-at_install", "post_install")
class TestPaymentPlaid(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Obtener (o crear) el proveedor de pago Plaid
        cls.provider_plaid = cls.env["payment.provider"].search(
            [("code", "=", "plaid_manual")], limit=1
        )
        if not cls.provider_plaid:
            cls.provider_plaid = cls.env["payment.provider"].create(
                {
                    "name": "Plaid (Bank Transfer)",
                    "code": "plaid_manual",
                    "fees_active": False,
                    "company_id": cls.env.company.id,
                    "plaid_env": "sandbox",
                    "plaid_client_id": "11affb5c86430217a2ec21cfc77a4d",
                }
            )
        cls.provider_plaid.state = (
            "enabled"  # habilitar el proveedor si estaba deshabilitado
        )
        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "bank"), ("company_id", "=", cls.env.company.id)], limit=1
        )
        if not cls.journal:
            cls.journal = cls.env["account.journal"].create(
                {
                    "name": "Test Bank Journal",
                    "type": "bank",
                    "code": "TBNK",
                    "company_id": cls.env.company.id,
                }
            )
        cls.provider_plaid.journal_id = cls.journal.id
        # Crear un partner de prueba para las transacciones
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Test Partner",
                "email": "test@example.com",
            }
        )
        # Tomar la moneda de la compañía (para montos en transacciones)
        cls.currency = cls.env.company.currency_id
        # Crear una transacción de pago de prueba usando el proveedor Plaid
        cls.transaction = cls.env["payment.transaction"].create(
            {
                "amount": 100.0,
                "currency_id": cls.currency.id,
                "provider_id": cls.provider_plaid.id,
                "partner_id": cls.partner.id,
                "reference": "TESTTXN123",
            }
        )
        # Instanciar el controlador a probar
        cls.controller = PlaidController()

    # ---- Pruebas del endpoint /payment/plaid/get_link_token ----

    def test_get_link_token_no_provider_id(self):
        res = self.controller.get_link_token()
        self.assertEqual(res, {"error": "provider_id not specified"})

    def test_get_link_token_no_transaction_id(self):
        """Si falta transaction_id, debe devolver error indicando su ausencia."""
        res = self.controller.get_link_token(provider_id=self.provider_plaid.id)
        self.assertEqual(res, {"error": "transaction_id not specified"})

    def test_get_link_token_invalid_transaction(self):
        fake_id = 99999
        res = self.controller.get_link_token(
            provider_id=self.provider_plaid.id, transaction_id=fake_id
        )
        self.assertEqual(res, {"error": "No valid payment transaction."})

        # Caso alternativo: transacción existe pero sin provider_id (no válido)
        tx_no_provider = self.env["payment.transaction"].create(
            {
                "amount": 1.0,
                "currency_id": self.currency.id,
                "partner_id": self.partner.id,
                "reference": "NOPROV",
                # no seteamos provider_id
            }
        )
        res2 = self.controller.get_link_token(
            provider_id=self.provider_plaid.id, transaction_id=tx_no_provider.id
        )
        self.assertEqual(res2, {"error": "No valid payment transaction."})

    def test_get_link_token_wrong_provider(self):
        other_provider = self.env["payment.provider"].create(
            {
                "name": "Dummy Provider",
                "code": "dummy_provider",
                "company_id": self.env.company.id,
            }
        )
        tx_other = self.env["payment.transaction"].create(
            {
                "amount": 50.0,
                "currency_id": self.currency.id,
                "provider_id": other_provider.id,
                "partner_id": self.partner.id,
                "reference": "TESTTXN999",
            }
        )
        res = self.controller.get_link_token(
            provider_id=other_provider.id, transaction_id=tx_other.id
        )
        self.assertEqual(
            res,
            {"error": "Not using 'plaid_manual' as payment provider."},
        )

    def test_get_link_token_success(self):
        dummy_data = {
            "link_token": "fake-token-ABC123",
            "expiration": "2025-01-01T00:00:00Z",
        }
        dummy_response = DummyResponse(status_code=200, data=dummy_data)
        # Parchear requests.post para simular respuesta exitosa de Plaid
        with patch(
            "odoo.addons.payment_plaid.controllers.controllers.requests.post",
            return_value=dummy_response,
        ) as mock_post:
            res = self.controller.get_link_token(
                provider_id=self.provider_plaid.id, transaction_id=self.transaction.id
            )
        self.assertTrue(mock_post.called)
        self.assertIn("/link/token/create", mock_post.call_args[0][0])
        self.assertEqual(res.get("link_token"), "fake-token-ABC123")
        self.assertIn("expiration", res)
        self.assertEqual(res["expiration"], "2025-01-01T00:00:00Z")

    def test_get_link_token_error_response_with_message(self):
        """Caso en que Plaid responde con error (status != 200) y mensaje de error."""
        dummy_error = {"error_message": "Invalid API keys"}
        dummy_response = DummyResponse(status_code=400, data=dummy_error)
        with patch(
            "odoo.addons.payment_plaid.controllers.controllers.requests.post",
            return_value=dummy_response,
        ):
            res = self.controller.get_link_token(
                provider_id=self.provider_plaid.id, transaction_id=self.transaction.id
            )
        # Debe devolver el mensaje de error proporcionado por Plaid
        self.assertEqual(res, {"error": "Invalid API keys"})

    def test_get_link_token_error_response_no_link(self):
        dummy_data = {"expiration": "2025-01-01T00:00:00Z"}
        dummy_response = DummyResponse(status_code=200, data=dummy_data)
        with patch(
            "odoo.addons.payment_plaid.controllers.controllers.requests.post",
            return_value=dummy_response,
        ):
            res = self.controller.get_link_token(
                provider_id=self.provider_plaid.id, transaction_id=self.transaction.id
            )
        self.assertEqual(res, {"error": "Error generating link_token"})

    def test_plaid_submit_missing_params(self):
        res = self.controller.plaid_submit()  # ninguna kwarg
        self.assertEqual(res, {"error": "Missing parameters."})
        res2 = self.controller.plaid_submit(public_token="abc", account_id="xyz")
        self.assertEqual(res2, {"error": "Missing parameters."})

    def test_plaid_submit_provider_mismatch(self):
        other_provider = self.env["payment.provider"].create(
            {
                "name": "Other Provider",
                "code": "other_code",
                "company_id": self.env.company.id,
            }
        )
        res = self.controller.plaid_submit(
            public_token="token123",
            account_id="acc_999",
            provider_id=other_provider.id,
            transaction_id=self.transaction.id,
        )
        self.assertEqual(res, {"error": "Invalid transaction or provider mismatch."})
        # Caso 2: transacción no existe
        res2 = self.controller.plaid_submit(
            public_token="token123",
            account_id="acc_999",
            provider_id=self.provider_plaid.id,
            transaction_id=99999,
        )
        self.assertEqual(res2, {"error": "Invalid transaction or provider mismatch."})

    @mute_logger(CONTROLLER_LOGGER)
    def test_plaid_submit_exchange_exception(self):
        tx = self.transaction
        # Asegurarse que la transacción inicial no está en estado error
        self.assertNotEqual(tx.state, "error")
        side_effects = [Exception("Exchange failure")]
        plaid_post_path = (
            "odoo.addons.payment_plaid.controllers.controllers.requests.post"
        )
        with patch(plaid_post_path, side_effect=side_effects):
            res = self.controller.plaid_submit(
                public_token="pub_token_test",
                account_id="acc_test",
                provider_id=self.provider_plaid.id,
                transaction_id=tx.id,
            )
        self.assertIn("Error exchanging token", res.get("error", ""))
        self.assertIn("Exchange failure", res.get("error", ""))
        tx.invalidate_cache()
        self.assertEqual(tx.state, "error")

    @mute_logger(CONTROLLER_LOGGER)
    def test_plaid_submit_exchange_error_response(self):
        tx = self.transaction
        dummy_exchange_err = DummyResponse(
            status_code=401, data={"error_message": "Invalid public token"}
        )
        with patch(
            "odoo.addons.payment_plaid.controllers.controllers.requests.post",
            return_value=dummy_exchange_err,
        ):
            res = self.controller.plaid_submit(
                public_token="bad_token",
                account_id="acc",
                provider_id=self.provider_plaid.id,
                transaction_id=tx.id,
            )
        expected_msg = "Failed to exchange public_token: Invalid public token"
        self.assertEqual(res, {"error": expected_msg})
        tx.invalidate_cache()
        self.assertNotEqual(tx.state, "error")

    @mute_logger(CONTROLLER_LOGGER)
    def test_plaid_submit_auth_exception(self):
        """Simular excepción al crear la autorización de transferencia."""
        tx = self.transaction
        dummy_exchange = DummyResponse(200, {"access_token": "test_access_token"})
        side_fx = [dummy_exchange, Exception("Auth step failure")]
        with patch(
            "odoo.addons.payment_plaid.controllers.controllers.requests.post",
            side_effect=side_fx,
        ):
            res = self.controller.plaid_submit(
                public_token="token_ok",
                account_id="acc_ok",
                provider_id=self.provider_plaid.id,
                transaction_id=tx.id,
            )
        self.assertIn("Error creating transfer authorization", res.get("error", ""))
        self.assertIn("Auth step failure", res.get("error", ""))
        tx.invalidate_cache()
        self.assertEqual(tx.state, "error")

    @mute_logger(CONTROLLER_LOGGER)
    def test_plaid_submit_auth_error_response(self):
        tx = self.transaction
        dummy_exchange = DummyResponse(200, {"access_token": "token_ok"})
        dummy_auth_err = DummyResponse(400, {"error_message": "Account not supported"})
        side_fx = [dummy_exchange, dummy_auth_err]
        with patch(
            "odoo.addons.payment_plaid.controllers.controllers.requests.post",
            side_effect=side_fx,
        ):
            res = self.controller.plaid_submit(
                public_token="token_ok",
                account_id="acc_ok",
                provider_id=self.provider_plaid.id,
                transaction_id=tx.id,
            )
        expected_msg = "Failed to create transfer authorization: Account not supported"
        self.assertEqual(res, {"error": expected_msg})
        tx.invalidate_cache()
        self.assertNotEqual(tx.state, "error")

    @mute_logger(CONTROLLER_LOGGER)
    def test_plaid_submit_transfer_exception(self):
        tx = self.transaction
        dummy_exchange = DummyResponse(200, {"access_token": "acc_token_ok"})
        dummy_auth = DummyResponse(200, {"authorization": {"id": "auth_test_id"}})
        side_fx = [dummy_exchange, dummy_auth, Exception("Transfer step failure")]
        with patch(
            "odoo.addons.payment_plaid.controllers.controllers.requests.post",
            side_effect=side_fx,
        ):
            res = self.controller.plaid_submit(
                account_id="acc_ok",
                provider_id=self.provider_plaid.id,
                transaction_id=tx.id,
            )
        self.assertIn("Missing parameters.", res.get("error", ""))
        self.assertEqual(tx.state, "draft")

    @mute_logger(CONTROLLER_LOGGER)
    def test_plaid_submit_transfer_error_response(self):
        tx = self.transaction
        dummy_exchange = DummyResponse(200, {"access_token": "acc_token_ok"})
        dummy_auth = DummyResponse(200, {"authorization": {"id": "auth_ok_id"}})
        dummy_transfer_err = DummyResponse(400, {"error_message": "insufficient funds"})
        side_fx = [dummy_exchange, dummy_auth, dummy_transfer_err]
        with patch(
            "odoo.addons.payment_plaid.controllers.controllers.requests.post",
            side_effect=side_fx,
        ):
            res = self.controller.plaid_submit(
                public_token="ok",
                account_id="acc_ok",
                provider_id=self.provider_plaid.id,
                transaction_id=tx.id,
            )
        self.assertEqual(res, {"error": "insufficient funds"})
        tx.invalidate_cache()
        self.assertNotEqual(tx.state, "done")

    def test_plaid_submit_success(self):
        tx = self.transaction
        dummy_exchange = DummyResponse(200, {"access_token": "access_test_token"})
        dummy_auth = DummyResponse(200, {"authorization": {"id": "auth_12345"}})
        dummy_transfer = DummyResponse(
            200, {"transfer": {"id": "trf_54321", "status": "pending"}}
        )
        side_fx = [dummy_exchange, dummy_auth, dummy_transfer]
        with patch(
            "odoo.addons.payment_plaid.controllers.controllers.requests.post",
            side_effect=side_fx,
        ):
            res = self.controller.plaid_submit(
                public_token="good_token",
                account_id="acc_001",
                provider_id=self.provider_plaid.id,
                transaction_id=tx.id,
            )
        self.assertEqual(res, {"result": "success", "redirect_url": "/payment/status"})
        tx.invalidate_cache()
        self.assertEqual(tx.state, "done")
        self.assertEqual(tx.provider_reference, "trf_54321")
        payment = self.env["account.payment"].search(
            [("payment_transaction_id", "=", tx.id)]
        )
        self.assertTrue(payment, "No payment created for the transaction")
        self.assertEqual(payment.amount, abs(tx.amount))
        self.assertEqual(payment.partner_id.id, tx.partner_id.commercial_partner_id.id)
        self.assertEqual(payment.state, "posted")

    def test_should_build_inline_form_plaid(self):
        res = self.provider_plaid._should_build_inline_form()
        self.assertTrue(res)

    def test_specific_rendering_values_includes_provider(self):
        tx = self.transaction
        render_vals = tx._get_specific_rendering_values({})
        self.assertIn("provider", render_vals)
        self.assertEqual(render_vals["provider"].id, tx.provider_id.id)

    def test_processing_values_includes_transaction_id(self):
        tx = self.transaction
        vals = tx._get_processing_values()
        self.assertIn("transactionId", vals)
        self.assertEqual(vals["transactionId"], tx.id)

    def test_create_payment_plaid(self):
        tx = self.env["payment.transaction"].create(
            {
                "amount": 77.0,
                "currency_id": self.currency.id,
                "provider_id": self.provider_plaid.id,
                "partner_id": self.partner.id,
                "reference": "TXNPAY77",
            }
        )
        payment = tx._create_payment()
        self.assertTrue(payment)
        self.assertEqual(payment._name, "account.payment")
        self.assertEqual(payment.payment_transaction_id.id, tx.id)
        self.assertEqual(payment.amount, abs(tx.amount))
        self.assertEqual(payment.state, "posted")
        self.assertEqual(payment.currency_id.id, tx.currency_id.id)
        self.assertEqual(
            payment.partner_id.commercial_partner_id.id,
            tx.partner_id.commercial_partner_id.id,
        )

    def test_create_payment_non_plaid(self):
        other_provider = self.env["payment.provider"].create(
            {
                "name": "Manual Pay",
                "code": "manual_test",
                "company_id": self.env.company.id,
            }
        )
        tx = self.env["payment.transaction"].create(
            {
                "amount": 12.0,
                "currency_id": self.currency.id,
                "provider_id": other_provider.id,
                "partner_id": self.partner.id,
                "reference": "TXNMANUAL",
            }
        )
        res = tx._create_payment()
        if res:
            self.assertEqual(res._name, "account.payment")
            self.assertEqual(res.state, "posted")
        else:
            self.assertFalse(res)
