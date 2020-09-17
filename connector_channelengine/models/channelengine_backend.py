# Copyright 2020 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval


class ChannelEngineBackend(models.Model):
    """A ChannelEngine backend corresponds to an account on the platform.
       An account can be used to sell products on different platforms (Channels)
       e.g. BackMarket, Amazon, ...
    """

    _name = "channelengine.backend"
    _inherit = ["connector.backend", "server.env.mixin"]
    _description = "ChannelEngine Backend"

    name = fields.Char()
    host = fields.Char(string="ChannelEngine url")
    api_key = fields.Char(string="API Key")
    _sql_constraints = [
        ("uniq_host", "unique (host)", "There can be at most one backend per host.")
    ]
    domain = fields.Char(
        default="[]", string="Domain", help="Domain used to export the products."
    )
    depends = fields.Char(compute="_compute_binding_depends", store=True)
    export_id = fields.Many2one(
        required=True,
        string="Mapping",
        comodel_name="ir.exports",
        help="Mapping used for the export.",
    )

    @property
    def _server_env_fields(self):
        env_fields = super()._server_env_fields
        env_fields.update({"api_key": {}})
        return env_fields

    @api.constrains("domain")
    def _domain_constraint(self):
        for backend in self:
            try:
                domain = safe_eval(backend.domain)
                self.env["product.product"].search(domain)
            except Exception as e:  # TODO: refine handling
                message = _("The domain is not correctly set. Original error:")
                full_message = "{}\n{}".format(message, e)
                raise ValidationError(full_message)

    @api.model
    def create(self, vals):
        result = super(ChannelEngineBackend, self).create(vals)
        result.check_all_domain()
        return result

    def write(self, vals):
        result = super(ChannelEngineBackend, self).write(vals)
        self.check_all_domain()
        return result

    @api.model
    def all_check_domain(self, products):
        all_backends = self.search([])
        all_backends._check_domain(products)

    def _check_domain(self, products):
        """Check whether each product moves in or out of the backend domain.
           If it is the case, we need to either create the corresponding binding
           or set it for removal.
        """
        Binding = self.env["channelengine.binding"]
        for backend in self:
            bdomain = safe_eval(backend.domain) + [("active", "=", True)]

            def bfilter(p, bkd=backend):  # E731
                return bkd not in p.mapped("binding_ids.backend_id")

            products_without_bindings = products.filtered(bfilter)
            products_to_bind = products_without_bindings.filtered_domain(bdomain)
            if products_to_bind:
                Binding.create_from_products(backend, products_to_bind)

            products_with_bindings = products - products_without_bindings
            products_to_remove = (
                products_with_bindings - products_with_bindings.filtered_domain(bdomain)
            )
            if products_to_remove:
                bindings = products_to_remove.mapped("binding_ids")
                rfilter = lambda b, bk=backend: b.backend_id == bk  # noqa
                bindings_to_remove = bindings.filtered(rfilter)
                bindings_to_remove.write({"state": "toremove", "exception": "ok"})
        products.write({"check_backends": False})

    @api.depends("export_id.export_fields")
    def _compute_binding_depends(self):
        """This function forces the setup of the binding class,
           so that the depends is updated with the latest list from the export.
        """
        depends = {}
        for record in self:
            depends[record] = str(record.export_fields())
        new_depends = {r: d for r, d in depends.items() if r.depends != d}

        if new_depends:
            Binding = self.env["channelengine.binding"]
            Binding._setup_fields()
            Binding._setup_complete()
            new_domain = [("backend_id", "in", [r.id for r in new_depends])]
            Binding.search(new_domain).write({"check_backends": True})

        for record in depends:
            record.depends = depends[record]

    def export_fields(self):
        self.ensure_one()
        field_names = self.export_id.mapped("export_fields.name")
        return [fn.replace("/", ".") for fn in field_names]

    @api.model
    def get_export_fields(self):
        """Returns the list of all fields that are exported in at least one backend.
           If there are many backends, the list is thus a superset of any binding's
           dependencies.
        """
        backends = self.search([])  # pre_init_hook makes this work at module install
        if backends:
            return sum(backends.mapped(lambda b: safe_eval(b.depends)), [])
        return []

    def check_all_domain(self):
        """Check for all products that they should be exported."""
        all_products = self.env["product.product"].search([])
        self._check_domain(all_products)

    def check_all_data(self):
        """Check the data for all existing bindings."""
        for backend in self:
            domain = [("backend_id", "=", backend.id)]
            all_bindings = self.env["channelengine.binding"].search(domain)
            all_bindings._compute_data()

    def check_all(self):
        """Check all existing bindings,
           then check all products for new or outdated bindings.
        """
        self.check_all_data()
        self.check_all_domain()

    @api.model
    def _work_by_backend(self, base_domain, limit=None):
        backends = self.search([])
        for backend in backends:
            domain = base_domain + [("backend_id", "=", backend.id)]
            todo = self.env["channelengine.binding"].search(domain, limit=limit)
            with backend.work_on(self._name, records=todo, backend=backend) as work:
                yield work

    def cron_update(self, limit=None):
        base_domain = [
            ("state", "in", ["new", "todo"]),
            ("check_backends", "=", False),
            ("exception", "!=", "exception"),
        ]
        for work in self._work_by_backend(base_domain, limit=limit):
            exporter = work.component(usage="record.exporter")
            exporter.run()

    def cron_remove(self, limit=None):
        base_domain = [("state", "=", "toremove"), ("exception", "!=", "exception")]
        for work in self._work_by_backend(base_domain, limit=limit):
            deleter = work.component(usage="record.deleter")
            deleter.run()

    def cron_check_data(self, limit=None):
        base_domain = [("check_backends", "=", True)]
        for work in self._work_by_backend(base_domain, limit=limit):
            work.records._compute_data()

    def cron_check_domain(self, limit=None):
        base_domain = [("check_backends", "=", True)]
        Products = self.env["product.product"].with_context(active_test=False)
        products = Products.search(base_domain, limit=limit)
        self.all_check_domain(products)
