# Copyright 2020 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

SYNC_STATUSES = [
    ("new", "New"),
    ("todo", "To Do"),
    ("toremove", "To Remove"),
    ("done", "Done"),
]

EXCEPTION_STATUSES = [
    ("ok", "OK"),
    ("warning", "Warning"),
    ("exception", "Exception"),
]


def read_per_record(self, fields=None, load="_classic_read"):
    # TODO: extract that in base_partition?
    result = {}
    data_list = self.read(fields=fields, load=load)
    for d in data_list:
        key = d.pop("id")
        result[key] = d
    return result


class ChannelengineBinding(models.Model):
    """Stores the data to export.
       The only possible interaction a user should have with it is set its
       exception state to OK after checking the message and solving the issues,
       when it is in warning or exception.
       So no create, copy, write, delete.
       We only forbid explicitly the unlink because we would lose information;
       in all other cases, if the user manually does something
       (e.g. add a binding for a product)
       then the various crons will restore the normal situation
       (so remove it if the product should not be exported,
       or it would have been created anyway).
    """

    _name = "channelengine.binding"
    _description = "ChannelEngine Product Binding"

    display_name = fields.Char(compute="_compute_display_name", store=True)
    backend_id = fields.Many2one(required=True, comodel_name="channelengine.backend")
    product_id = fields.Many2one(required=True, comodel_name="product.product")
    state = fields.Selection(SYNC_STATUSES, readonly=True, required=True, default="new")
    check_backends = fields.Boolean(default=True, readonly=True, required=True)
    exception = fields.Selection(
        EXCEPTION_STATUSES, readonly=True, required=True, default="ok"
    )
    message = fields.Text(readonly=True)
    data = fields.Serialized(compute="_compute_data", store=True)

    _sql_constraints = [
        (
            "uniq_backend_product",
            "unique (backend_id, product_id)",
            "There can be at most one binding per backend and product couple.",
        ),
    ]

    @api.model
    def create_from_products(self, backend, products):
        to_create = []
        for product in products:
            record = {
                "backend_id": backend.id,
                "product_id": product.id,
            }
            to_create.append(record)
        return self.create(to_create)

    @api.model
    def get_export_fields(self):
        product_fields = self.backend_id.get_export_fields()
        return ["product_id." + f for f in product_fields]

    @api.depends(lambda self: self.get_export_fields())
    def _compute_data(self):
        old_data = read_per_record(self, ["data"])
        bindings_toprocess = self.filtered(lambda s: s.state != "toremove")
        bindings_per_backend = bindings_toprocess.partition("backend_id")
        for backend in bindings_per_backend:
            parser = backend.export_id.get_json_parser()
            records = bindings_per_backend[backend]
            datas = records.mapped("product_id").jsonify(parser)  # TODO?
            for record, data in zip(records, datas):
                if data != old_data.get(record.id, {}).get("data"):
                    record.mark_todo()
                else:
                    record.check_backends = False
                record.data = data

    def mark_tocheck(self, force_todo=False):
        for record in self:
            record.check_backends = True
            if force_todo:
                record.state = "todo"

    def mark_toremove(self):
        for record in self:
            record.state = "toremove"
            record.exception = "ok"

    def mark_todo(self):
        for record in self:
            record.state = "todo"
            record.exception = "ok"
            record.check_backends = False

    def mark_exception(self):
        for record in self:
            record.exception = "exception"

    def mark_done(self, with_warning=False):
        for record in self:
            record.state = "done"
            record.exception = "warning" if with_warning else "ok"

    @api.depends("product_id.name", "backend_id.name")
    def _compute_display_name(self):
        for record in self:
            backend_name = record.backend_id.name or "_"
            product_name = record.product_id.name or "_"
            record.display_name = "{}/{}".format(backend_name, product_name)

    def unlink(self):
        if not self.env.context.get("synchronized"):
            raise ValidationError(
                _(
                    "Bindings cannot be removed manually."
                    "It would be recreated automatically anyway, so it does make sense."
                    "Thus a user should just make sure the corresponding "
                    "product is out of the backend's domain,"
                    " and let the cron do the rest."
                )
            )
        return super(ChannelengineBinding, self).unlink()
