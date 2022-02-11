odoo.define('FAE_app.load_document', function (require) {
    "use strict";

    var core = require('web.core');
    var ListView = require('web.ListView');
    var ListController = require('web.ListController');

    var includeDict = {
        renderButtons: function () {
            this._super.apply(this, arguments);
            if (this.$buttons) {            
                if (this.modelName === "xfae.incoming.documents"){
                    var buttonLoad = this.$buttons.find('button.o_button_help')
                    buttonLoad.on('click', this.proxy('o_button_help'))
                }
            }
        },

        o_button_help: function () {
            var self = this;
            var state = self.model.get(self.handle, {raw: true});
            return self.do_action({
                name: 'Cargar Documento',
                type: 'ir.actions.act_window',
                res_model: 'xfae.read_local_doc',
                target: 'new',
                views: [[false, 'form']],
                view_type: 'form',
                view_mode: 'form',
                flags: {'form': {'action_buttons':true, 'options':{'mode': 'edit'}}}
            });
        }

    };
    ListController.include(includeDict);

});

