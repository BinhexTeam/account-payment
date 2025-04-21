from odoo import fields, models


class PaymentProviderPlaid(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(
        selection_add=[("plaid_manual", "Plaid (Bank Transfer)")],
        ondelete={"plaid_manual": "set default"},
    )

    plaid_env = fields.Selection(
        [
            ("sandbox", "Sandbox"),
            ("development", "Development"),
            ("production", "Production"),
        ],
        string="Plaid Environment",
        default="sandbox",
        help="Plaid environment to use (Sandbox, Development or Production).",
    )
    plaid_client_id = fields.Char("Client ID", help="Client ID provided by Plaid")
    plaid_secret = fields.Char("Secret", help="Secret Key provided by Plaid")

    def _should_build_inline_form(self, is_validation=False):
        """Forzar el uso de formulario integrado (inline) en nuestros métodos Plaid."""
        self.ensure_one()
        if self.code in ("plaid_manual"):
            return True
        return super()._should_build_inline_form(is_validation)

    def _get_supported_payment_flows(self):
        if self.code == "plaid_manual":
            return ["direct"]
        return super()._get_supported_payment_flows()
