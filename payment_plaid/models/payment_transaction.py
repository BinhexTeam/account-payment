from odoo import api, models


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    @api.model
    def _get_specific_rendering_values(self, processing_values):
        rendering_values = super()._get_specific_rendering_values(processing_values)
        rendering_values["provider"] = self.provider_id
        return rendering_values

    def _get_processing_values(self):
        res = super()._get_processing_values()
        res.update({"transactionId": self.id})
        return res

    def _create_payment(self, **extra_create_values):
        self.ensure_one()

        if self.provider_id.code != "plaid_manual":
            return super()._create_payment(**extra_create_values)

        journal = self.provider_id.journal_id
        provider_id = self.provider_id.id
        payment_method_line = journal.inbound_payment_method_line_ids.filtered(
            lambda line: line.payment_provider_id.id == provider_id
        )

        payment_values = {
            "amount": abs(self.amount),
            "payment_type": "inbound",
            "currency_id": self.currency_id.id,
            "partner_id": self.partner_id.commercial_partner_id.id,
            "partner_type": "customer",
            "journal_id": self.provider_id.journal_id.id,
            "company_id": self.provider_id.company_id.id,
            "payment_method_line_id": payment_method_line[:1].id or None,
            "ref": f"{self.reference} - {self.partner_id.name}",
            **extra_create_values,
        }

        payment = self.env["account.payment"].sudo().create(payment_values)
        payment.action_post()
        self.payment_id = payment
        if self.invoice_ids:
            self.invoice_ids.filtered(lambda inv: inv.state == "draft").action_post()
            (payment.line_ids + self.invoice_ids.line_ids).filtered(
                lambda line: line.account_id == payment.destination_account_id
            ).reconcile()

        return payment
