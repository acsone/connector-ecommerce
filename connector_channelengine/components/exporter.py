# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo.addons.component.core import Component


class ChannelEngineExporter(Component):
    _name = "channelengine.exporter"
    _inherit = ["channelengine.connector", "base.exporter"]
    _usage = "record.exporter"
    _base_backend_adapter_usage = "backend.adapter"

    def run(self):
        return self.backend_adapter.export(self.work.records)
