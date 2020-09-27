from odoo import _, api, fields, models
from odoo.exceptions import Warning as OdooWarning


class ChannelengineBackendConfiguration(models.TransientModel):
    _name = "channelengine.backend.configuration"
    _description = "ChannelEngine Backend Configuration Check"

    @api.model
    def _default_backend(self):
        return self.env["channelengine.backend"].search([], limit=1)

    backend_id = fields.Many2one(
        "channelengine.backend", string="Tested backend", default=_default_backend
    )
    export_id = fields.Many2one("ir.exports", string="Tested Export", required=True)
    assortment_id = fields.Many2one(
        "ir.filters",
        string="Test Assortment",
        domain=[("is_assortment", "=", True)],
        required=True,
    )
    limit = fields.Integer(
        string="Limit number of products to check (0 for all products)", default=0
    )

    @api.onchange("backend_id")
    def onchange_backend(self):
        self.assortment_id = self.backend_id.assortment_id
        self.export_id = self.backend_id.export_id
        return {}

    def check_configuration(self):
        domain = self.backend_id.assortment_id._get_eval_domain()
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
