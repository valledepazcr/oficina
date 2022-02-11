odoo.define('FAE_app.read_emails', function (require){
    "use strict";

    var ajax = require('web.ajax');
    var ListController = require('web.ListController');
    var rpc = require('web.rpc')

    var includeDict = {
        renderButtons: function($node) {
            this._super.apply(this, arguments);
            var self = this;
            if (this.$buttons) {
                $(this.$buttons).find('.o_read_email').on('click', function() {
                    rpc.query({
                        model: 'xfae.incoming.documents',
                        method: 'read_email',
                        args: [[this.id]],
                    }).then(function(res){
                        // console.log(res)
                        // self.reload();
                    })
                });
            }
        },
    };

    ListController.include(includeDict);
});
