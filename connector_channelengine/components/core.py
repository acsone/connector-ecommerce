# Copyright 2020 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.addons.component.core import Component


class ChannelEngineConnectorComponent(Component):
    _name = "channelengine.connector"
    _inherit = "base.connector"
    _collection = "channelengine.backend"
