# Copyright 2020 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ChannelEngineChannel(models.Model):

    _name = "channelengine.channel"
    _description = "ChannelEngine Channel"

    name = fields.Char(string="Channel Name")
    technical_name = fields.Char(string="Channel Technical Name")
    domain = fields.Char(string="Domain")
    default = fields.Boolean(default=False)
    _sql_constraints = [
        ("uniq_name", "unique (name)", "Channel names should be unique.")
    ]

    def get_default_ids(self):
        return self.search([("default", "=", True)]).ids
