# Copyright 2018 ACSONE SA/NV (<http://acsone.eu>)
# Copyright 2018 Akretion (http://www.akretion.com).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo.addons.component.core import Component


class ChannelEngineDeleter(Component):
    _name = "channelengine.deleter"
    _inherit = ["channelengine.connector", "base.deleter"]
    _usage = "record.deleter"
    _base_backend_adapter_usage = "backend.adapter"

    def run(self):
        return self.backend_adapter.delete(self.work.records)
