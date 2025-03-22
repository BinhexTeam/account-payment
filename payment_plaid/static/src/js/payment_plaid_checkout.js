/** @odoo-module **/
odoo.define("payment_plaid.payment_form", (require) => {
    "use strict";

    const checkoutForm = require("payment.checkout_form");
    const manageForm = require("payment.manage_form");
    const Dialog = require("web.Dialog");
    const core = require("web.core");
    const _t = core._t;

    const Plaid = window.Plaid || null;

    const paymentPlaidMixin = {
        /**
         * Sobrescribimos el método genérico de procesar Redirecciones.
         * @override
         */
        _processRedirectPayment: function (code, paymentOptionId, processingValues) {
            if (code !== "plaid_manual") {
                return this._super(...arguments);
            }

            // 1) Obtenemos el transactionId de processingValues
            //    (se genera en el backend en _get_processing_values)
            const transactionId = processingValues.transactionId || processingValues.id;

            // 2) Llamamos a nuestro endpoint /payment/plaid/get_link_token
            return this._rpc({
                route: "/payment/plaid/get_link_token",
                params: {
                    provider_id: paymentOptionId,
                    transaction_id: transactionId,
                },
            }).then((response) => {
                if (response.error) {
                    return this._displayError(
                        _t("Error"),
                        _t("Failed to generate Plaid Link Token."),
                        response.error
                    );
                }

                const linkToken = response.link_token;
                const handler = Plaid.create({
                    token: linkToken,
                    onSuccess: (public_token, metadata) => {
                        const accounts = metadata.accounts;
                        if (accounts.length > 1) {
                            this._showAccountSelection(accounts)
                                .then((account_id) => {
                                    this._submitPlaidTransfer(
                                        public_token,
                                        account_id,
                                        transactionId,
                                        paymentOptionId
                                    );
                                })
                                .catch((err) =>
                                    this._displayError(
                                        _t("Error"),
                                        _t("Selection canceled or error."),
                                        err
                                    )
                                );
                        } else {
                            this._submitPlaidTransfer(
                                public_token,
                                accounts[0].id,
                                transactionId,
                                paymentOptionId
                            );
                        }
                    },
                    onExit: (err) => {
                        if (err) {
                            this._displayError(
                                _t("Error"),
                                _t("Plaid was canceled or there was a mistake."),
                                err.display_message || err.message
                            );
                        }
                    },
                });
                handler.open();
            });
        },

        /**
         * Muestra un diálogo para elegir la cuenta bancaria si hay varias.
         */
        _showAccountSelection: function (accounts) {
            return new Promise((resolve, reject) => {
                const $modalContent = $(`
                    <div class="list-group">
                        ${accounts
                            .map(
                                (acc) => `
                            <button type="button" class="list-group-item list-group-item-action" data-account-id="${acc.id}">
                                ${acc.name} ****${acc.mask} (${acc.subtype})
                            </button>`
                            )
                            .join("")}
                    </div>`);

                const modal = new Dialog(this, {
                    title: _t("Select your bank account"),
                    $content: $modalContent,
                    buttons: [{text: _t("Cancel"), close: true}],
                    onClose: () => reject(_t("Selection canceled.")),
                });

                modal.opened().then(() => {
                    $modalContent.on("click", "button[data-account-id]", function () {
                        const account_id = $(this).data("account-id");
                        resolve(account_id);
                        modal.close();
                    });
                });

                modal.open();
            });
        },

        /**
         * Llama a nuestro endpoint para hacer la transferencia en Plaid
         * y, en caso de éxito, redirigir al usuario.
         */
        _submitPlaidTransfer: function (
            public_token,
            account_id,
            transactionId,
            providerId
        ) {
            return this._rpc({
                route: "/payment/plaid/submit",
                params: {
                    public_token,
                    account_id,
                    provider_id: providerId,
                    transaction_id: transactionId,
                },
            })
                .then((response) => {
                    if (response.result === "success") {
                        window.location =
                            response.redirect_url || "/payment/confirmation";
                    } else if (response.result === "error") {
                        window.location = response.redirect_url || "/payment/status";
                    } else if (response.error) {
                        // Error inesperado
                        Dialog.alert(this, {
                            title: _t("Error"),
                            size: "medium",
                            $content: $("<div>").text(
                                response.error || _t("Unknown payment error.")
                            ),
                        });
                    }
                })
                .catch((error) => {
                    Dialog.alert(this, {
                        title: _t("Payment Error"),
                        size: "medium",
                        $content: $("<p/>").text(
                            error.message || _t("Unexpected error.")
                        ),
                    });
                });
        },
    };

    checkoutForm.include(paymentPlaidMixin);
    manageForm.include(paymentPlaidMixin);
});
