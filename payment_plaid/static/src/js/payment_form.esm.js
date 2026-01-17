/** @odoo-module **/
import PaymentForm from "@payment/js/payment_form";
import {_t} from "@web/core/l10n/translation";

const Plaid = window.Plaid || null;

PaymentForm.include({
    /* eslint-disable no-unused-vars */
    async _prepareInlineForm(
        providerId,
        providerCode,
        paymentOptionId,
        paymentMethodCode,
        flow
    ) {
        /* eslint-enable no-unused-vars */

        if (providerCode !== "plaid_manual") {
            return this._super(...arguments);
        }
        this._setPaymentFlow("direct");
    },

    async _processDirectFlow(
        providerCode,
        paymentOptionId,
        paymentMethodCode,
        processingValues
    ) {
        if (providerCode !== "plaid_manual") {
            return this._super(...arguments);
        }

        const transactionId = processingValues.transactionId || processingValues.id;
        const provider_id = processingValues.provider_id || null;

        let response = null;
        try {
            response = await this.rpc("/payment/plaid/get_link_token", {
                provider_id,
                transaction_id: transactionId,
            });
        } catch (error) {
            this._displayErrorDialog(_t("Error"), error.message);
            return;
        }

        if (response.error) {
            this._displayErrorDialog(_t("Plaid Error"), response.error);
            return;
        }

        $(".o_blockUI").remove();

        const handler = Plaid.create({
            token: response.link_token,
            onSuccess: async (public_token, metadata) => {
                const accounts = metadata.accounts;
                let account_id = null;

                if (accounts.length > 1) {
                    try {
                        account_id = await this._showAccountSelection(accounts);
                        if (!account_id) return;
                    } catch (e) {
                        this._displayErrorDialog(_t("Error"), e.message);
                        return;
                    }
                } else {
                    account_id = accounts[0].id;
                }

                await this._submitPlaidTransfer(
                    public_token,
                    account_id,
                    transactionId,
                    provider_id
                );
            },
            onExit: (err) => {
                if (err) {
                    this._displayErrorDialog(
                        _t("Plaid Error"),
                        err.display_message || err.message
                    );
                }
            },
        });

        handler.open();
    },

    _showAccountSelection(accounts) {
        return new Promise((resolve) => {
            const modalId = `plaidAccountModal_${Date.now()}`;
            let isResolved = false;

            const buttonsHtml = accounts
                .map(
                    (acc) => `
                <button type="button"
                        class="btn btn-primary my-2 w-100 account-btn"
                        data-account-id="${acc.id}">
                    ${acc.name} ****${acc.mask} (${acc.subtype})
                </button>
            `
                )
                .join("");

            const modalHtml = `
                <div class="modal fade" id="${modalId}" tabindex="-1" role="dialog" aria-hidden="true">
                  <div class="modal-dialog" role="document">
                    <div class="modal-content">
                      <div class="modal-header">
                        <h5 class="modal-title">${_t("Select your bank account")}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                      </div>
                      <div class="modal-body">
                        <p>${_t(
                            "Please select the bank account to use for payment:"
                        )}</p>
                        ${buttonsHtml}
                      </div>
                      <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">${_t(
                            "Cancel"
                        )}</button>
                      </div>
                    </div>
                  </div>
                </div>`;

            const $modal = $(modalHtml).appendTo("body");

            $modal.on("click", ".account-btn", function () {
                if (!isResolved) {
                    isResolved = true;
                    const id = $(this).data("account-id");
                    resolve(id);
                    $modal.modal("hide");
                }
            });

            $modal.on("hidden.bs.modal", function () {
                if (!isResolved) {
                    isResolved = true;
                    resolve(null);
                }
                $modal.remove();
            });

            $modal.modal("show");
        });
    },

    async _submitPlaidTransfer(public_token, account_id, transactionId, providerId) {
        try {
            const response = await this.rpc("/payment/plaid/submit", {
                public_token,
                account_id,
                provider_id: providerId,
                transaction_id: transactionId,
            });

            if (response.result === "success") {
                window.location = response.redirect_url || "/payment/confirmation";
            } else if (response.result === "error") {
                window.location = response.redirect_url || "/payment/status";
            } else if (response.error) {
                this._displayErrorDialog(_t("Plaid Error"), response.error);
            }
        } catch (error) {
            this._displayErrorDialog(_t("Payment Error"), error.message);
        }
    },

    _displayErrorDialog(title, message) {
        const modalId = `plaidErrorModal_${Date.now()}`;
        const modalHtml = `
            <div class="modal fade" id="${modalId}" tabindex="-1" role="dialog" aria-hidden="true">
              <div class="modal-dialog" role="document">
                <div class="modal-content">
                  <div class="modal-header">
                    <h5 class="modal-title">${title}</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                  </div>
                  <div class="modal-body">
                    <p>${message}</p>
                  </div>
                  <div class="modal-footer">
                    <button type="button" class="btn btn-primary" data-bs-dismiss="modal">OK</button>
                  </div>
                </div>
              </div>
            </div>`;
        const $modal = $(modalHtml).appendTo("body");
        $modal.on("hidden.bs.modal", () => $modal.remove());
        $modal.modal("show");
    },
});
