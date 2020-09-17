from odoo import _, api, fields, models
from odoo.exceptions import Warning as OdooWarning
from odoo.tools import safe_eval


class ChannelengineBackendConfiguration(models.TransientModel):
    _name = "channelengine.backend.configuration"
    _description = "ChannelEngine Backend Configuration Check"

    @api.model
    def _default_backend(self):
        return self.env["channelengine.backend"].search([], limit=1)

    @api.model
    def _default_domain(self):
        return self.backend_id.domain

    @api.model
    def _default_export(self):
        return self.backend_id.export_id

    backend_id = fields.Many2one(
        "channelengine.backend", string="Tested backend", default=_default_backend
    )
    export_id = fields.Many2one(
        "ir.exports", string="Tested Export", default=_default_export
    )
    domain = fields.Char(string="Test Domain", default=_default_domain)
    limit = fields.Integer(
        string="Limit number of products to check (0 for all products)", default=0
    )

    @api.onchange("backend_id")
    def onchange_backend(self):
        self.domain = self.backend_id.domain
        self.export_id = self.backend_id.export_id
        return {}

    def check_configuration(self):
        domain = safe_eval(self.domain)
        products = self.env["product.product"].search(domain, limit=self.limit or None)
        parser = self.export_id.get_json_parser()
        data = products.jsonify(parser)  # TODO?
        message = ""
        merchant_ids = {d.get("MerchantProductNo") for d in data}
        if len(merchant_ids) < len(products):
            message += "\n" + _("The MerchantProductNo are not uniques.")
        if None in merchant_ids or "" in merchant_ids:
            message += "\n" + _("Some products do not have a MerchantProductNo set.")
        # TODO: check images, ...
        if message == "":
            message = _("Everything looks properly configured.")
        raise OdooWarning(message)
