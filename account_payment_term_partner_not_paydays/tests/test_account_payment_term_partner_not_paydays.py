# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.base.tests.common import BaseCommon


@tagged("post_install", "-at_install")
class TestAccountPaymentTermPartnerNotPaydays(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.product = cls.env["product.product"].create({"name": "Product Test"})

    def enable_config_days_not_pay(self):
        conf = self.env["res.config.settings"].create({"days_not_pay": True})
        conf.execute()

    def create_partner(self, **values):
        range_not_pay_days = [
            Command.create({"date_start": "2025-08-01", "date_end": "2025-08-31"})
        ]
        create_values = {"name": "Partner Test", "customer_payment_days": "5,17"}
        if values.get("failed_range", False):
            range_not_pay_days.append(
                Command.create({"date_start": "2025-08-06", "date_end": "2025-08-23"})
            )
        create_values.update({"partner_not_pay_ids": range_not_pay_days})
        return self.env["res.partner"].create(create_values)

    def create_invoice(self, **values):
        partner_id = self.create_partner()
        create_values = {
            "partner_id": partner_id.id,
            "company_id": self.company.id,
            "invoice_date": "2025-07-15",
            "invoice_date_due": "2025-08-15",
            "move_type": values.get("move_type", "out_invoice"),
            "invoice_payment_term_id": self.env.ref(
                "account.account_payment_term_30days"
            ).id,
        }
        if values.get("add_lines", False):
            create_values.update(
                {
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "Test",
                                "product_id": self.product.id,
                                "debit": 100,
                                "credit": 0,
                            }
                        )
                    ]
                }
            )

        return self.env["account.move"].create(create_values)

    def test_overlap_days_not_pay(self):
        self.enable_config_days_not_pay()
        invoice = self.create_invoice()
        self.assertTrue(invoice.message_range_not_pay)
        self.assertIn("01/08/2025", invoice.message_range_not_pay)
        self.assertIn("31/08/2025", invoice.message_range_not_pay)
        invoice_entry = self.create_invoice(
            **{
                "move_type": "entry",
            }
        )
        self.assertFalse(invoice_entry.message_range_not_pay)

    def test_action_post(self):
        self.enable_config_days_not_pay()
        invoice = self.create_invoice(
            **{
                "add_lines": True,
            }
        )
        invoice.action_post()
        self.assertEqual(invoice.invoice_date_due, date(2025, 9, 17))

    def test_check_date_start_end(self):
        with self.assertRaises(ValidationError):
            self.create_partner(
                **{
                    "failed_range": True,
                }
            )
