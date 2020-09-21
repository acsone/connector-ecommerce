# Copyright 2020 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import os.path as path

from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    channel_ids = fields.Many2many(
        string="ChannelEngine Channels",
        help="Use these tags to filter on which channels to export",
        comodel_name="channelengine.channel",
        default=lambda self: self.env["channelengine.channel"].get_default_ids(),
    )


class Product(models.Model):
    _inherit = "product.product"

    binding_ids = fields.One2many("channelengine.binding", "product_id", copy=False)
    check_backends = fields.Boolean(
        copy=False,
        string="Check backend domains",
        required=True,
        default=True,
        help="Whether this product needs to be checked for backend domains.",
    )
    category_trail = fields.Char(compute="_compute_category_trail", store=True)
    channelengine_parent = fields.Char(
        compute="_compute_merchant_parent",
        store=True,
        readonly=True,
        default=False,
        help="Technical field used by ChannelEngine."
        "This value is set iff the product has more than one variant.",
    )

    def write(self, vals):
        """Whenever we write on a product, it might move the product in or out
           of some backend domains. Thus it needs to be checked.
        """
        if "check_backends" not in vals:
            vals["check_backends"] = True
        return super(Product, self).write(vals)

    @api.depends("categ_id.complete_name")
    def _compute_category_trail(self):
        for record in self:
            category_name = record.categ_id.complete_name or "_"
            record.category_trail = category_name.replace("/", ">")

    @api.depends("product_tmpl_id.product_variant_ids.default_code")
    def _compute_merchant_parent(self):
        for rec in self:
            if len(rec.product_tmpl_id.product_variant_ids) > 1:
                parent = "P{}".format(rec.product_tmpl_id.id)
                codes = rec.product_tmpl_id.product_variant_ids.mapped("default_code")
                nonempty_codes = [c for c in codes if c]
                prefix = path.commonprefix(nonempty_codes)
                parent = "{}_{}".format(parent, prefix) if prefix else parent
                rec.channelengine_parent = parent
            else:
                rec.channelengine_parent = False
