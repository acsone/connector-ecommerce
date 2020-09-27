# Copyright 2020 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ChannelEngineChannel(models.Model):

    _name = "channelengine.channel"
    _description = "ChannelEngine Channel"

    name = fields.Char(required=True, string="Channel Name")
    default = fields.Boolean(default=False)
    _sql_constraints = [
        ("uniq_name", "unique (name)", "Channel names should be unique.")
    ]

    @api.model
    def get_default_ids(self):
        return self.search([("default", "=", True)]).ids
