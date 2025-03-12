odoo.define('payment_plaid.payment_form', require => {
    'use strict';

    const checkoutForm = require('payment.checkout_form');
    const manageForm = require('payment.manage_form');
    const Dialog = require('web.Dialog');
    const core = require('web.core');
    const _t = core._t;


    const paymentPlaidMixin = {

        _processRedirectPayment: function (code, providerId, processingValues) {
            if (code !== 'plaid_manual') {
                return this._super(...arguments);
            }
    
            return this._rpc({
                route: '/payment/plaid/get_link_token',
                params: { provider_id: providerId },
            }).then(response => {
                const linkToken = response.link_token;
                const handler = Plaid.create({
                    token: linkToken,
                    onSuccess: (public_token, metadata) => {
                        const accounts = metadata.accounts;
                        if (accounts.length > 1) {
                            this._showAccountSelection(accounts).then(account_id => {
                                this._submitPlaidTransfer(public_token, account_id, providerId)
                                    .then(() => window.location = '/payment/status');
                            }).catch(err => this._displayError(
                                _t("Error"),
                                _t("Selection canceled or error."),
                                err
                            ));
                        } else {
                            this._submitPlaidTransfer(public_token, accounts[0].id, providerId)
                                .then(() => window.location = '/payment/status');
                        }
                    },
                    onExit: err => {
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

        _showAccountSelection: function(accounts) {
            return new Promise((resolve, reject) => {
                const $modalContent = $(`
                    <div class="list-group">
                        ${accounts.map(acc => `
                            <button type="button" class="list-group-item list-group-item-action" data-account-id="${acc.id}">
                                ${acc.name} ****${acc.mask} (${acc.subtype})
                            </button>`).join('')}
                    </div>`);

                const modal = new Dialog(this, {
                    title: _t('Select your bank account'),
                    $content: $modalContent,
                    buttons: [
                        { text: _t('Cancel'), close: true }
                    ],
                    onClose: () => reject(_t('Selection canceled.')),
                });

                modal.opened().then(() => {
                    $modalContent.on('click', 'button[data-account-id]', function() {
                        const account_id = $(this).data('account-id');
                        resolve(account_id);
                        modal.close();
                    });
                });

                modal.open();
            });
        },
          

        _submitPlaidTransfer: function(public_token, account_id, provider_id) {
            return this._rpc({
                route: '/payment/plaid/submit',
                params: { public_token, account_id, provider_id },
            }).then(response => {
                if (response.result !== 'success') {
                    alert(response.error || 'Plaid transfer error.');
                    throw new Error(response.error);
                }
            });
        },
    };

    checkoutForm.include(paymentPlaidMixin);
    manageForm.include(paymentPlaidMixin);
});
