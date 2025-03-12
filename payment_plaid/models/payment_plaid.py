from odoo import fields, models


class PaymentProviderPlaid(models.Model):
    _inherit = "payment.provider"

    # Agregar las nuevas opciones al campo de selección 'code'
    code = fields.Selection(
        selection_add=[("plaid_manual", "Plaid (Bank Transfer)")],
        ondelete={"plaid_manual": "set default"},
    )

    # Campos de configuración de Plaid
    plaid_env = fields.Selection(
        [
            ("sandbox", "Sandbox"),
            ("development", "Development"),
            ("production", "Production"),
        ],
        string="Plaid Environment",
        default="sandbox",
        help="Plaid environment to use (Sandbox for testing, Development or Production).",
    )
    plaid_client_id = fields.Char("Client ID", help="Client ID provided by Plaid")
    plaid_secret = fields.Char("Secret", help="Secret Key provided by Plaid")

    def _should_build_inline_form(self, is_validation=False):
        """Forzar el uso de formulario integrado (inline) en nuestros métodos Plaid."""
        self.ensure_one()
        if self.code in ("plaid_manual"):
            # Siempre usamos formulario inline (no redirección) para Plaid
            return True
        # Caso contrario, usar comportamiento por defecto
        return super(PaymentProviderPlaid, self)._should_build_inline_form(
            is_validation
        )
