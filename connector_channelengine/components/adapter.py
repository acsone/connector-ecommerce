# Copyright 2019 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
from datetime import datetime

from channelengine_merchant_api_client import ApiClient, Configuration, ProductApi
from channelengine_merchant_api_client.rest import ApiException

from odoo.addons.component.core import Component
from odoo.addons.queue_job.exception import RetryableJobError

_logger = logging.getLogger(__name__)


class ChannelEngineAdapter(Component):
    """We can export at most 10000 products at a time.
       However, we need to enrich the data with parent's data (essentially the template)
       if the products have sibling variants. In the worst case, for products we export
       we have one parent, but we are updating only one variant for each; so to be sure
       we need to stop at 5000.
    """

    _name = "channelengine.adapter"
    _inherit = ["base.backend.adapter", "channelengine.connector"]
    _usage = "backend.adapter"

    def _get_api_client(self):
        config = Configuration()
        config.host = self.work.backend.host
        config.api_key["apiKey"] = self.work.backend.api_key
        return ApiClient(config)

    def _get_product_client(self):
        """Create or overwrite product.
           It is not possible to write only specific attributes, except stock/quantity
           through the offer client. So all fields should be passed.
        """
        return ProductApi(self._get_api_client())

    def _export_parents(self, bindings, product_data):
        parents = []
        processed = set()
        for b, pd in zip(bindings, product_data):
            parent_no = pd.get("ParentMerchantProductNo")
            if parent_no and parent_no not in processed:
                processed.add(parent_no)
                parent_json = {}
                parent_json["Name"] = b.product_id.product_tmpl_id.display_name
                parent_json["MerchantProductNo"] = parent_no
                parents.append(parent_json)
        return parents

    def export(self, bindings):
        done = bindings.browse()
        warning = bindings.browse()
        exception = bindings.browse()
        for batch in bindings.batch(5000):
            client = self._get_product_client()
            product_data = batch.mapped("data")
            parent_data = self._export_parents(bindings, product_data)
            data = parent_data + product_data
            try:
                response = client.product_create(merchant_product_request=data)
            except ApiException as e:
                _logger.exception("[CEC] {}".format(e))
                exception |= batch
            except Exception as e:  # TODO: refine handling (e.g. 500 status)
                message = "[CEC] {}".format(e)
                _logger.exception(message)
                raise RetryableJobError(message)
            else:
                done, warning, exception = self._process_response_messages(
                    batch, response, done, warning, exception
                )
        return self._process_export_done_exception(done, warning, exception)

    def _process_export_done_exception(self, done, warning, exception):
        done.mark_done()
        warning.mark_done(with_warning=True)
        exception.mark_exception()
        return done, warning, exception

    def _process_response_messages(self, bindings, response, done, warning, exception):
        # warning: 'accepted_count' may not valid if there are products without
        # MerchantProductNo (these are automatically rejected).
        if not response.success:
            exception |= bindings
            return done, warning, exception
        new_exceptions = bindings.browse()
        for message in response.content.product_messages:
            binding = bindings.filtered(
                lambda b, name=message.name: b.data["Name"] == name
            )
            if message.errors:
                new_exceptions |= binding
            elif message.warnings:
                warning |= binding
            if message.warnings or message.errors:
                timestamp = ["Date: {}".format(datetime.now())]
                all_messages = timestamp + message.warnings + message.errors
                binding.write({"message": "\n\n".join(all_messages)})
        if not len(new_exceptions) == response.content.rejected_count:
            _logger.warning(
                "[CEC] Number of exceptions improperly processed: {}".format(response)
            )
        done |= bindings - new_exceptions
        exception |= new_exceptions
        return done, warning, exception

    def delete(self, bindings):
        client = self._get_product_client()
        done = bindings.browse()
        warning = bindings.browse()
        exception = bindings.browse()
        for binding in bindings:
            key = binding.data["MerchantProductNo"]
            try:
                response = client.product_delete(merchant_product_no=key)
            except ApiException as e:
                _logger.exception("[CEC] {}".format(e))
                if "The product could not be found" in e.body or not key:
                    done |= binding  # the product is already removed
                else:
                    exception |= binding
            else:
                if response.success is True:
                    done |= binding
                else:
                    message = response.message
                    log = "[CEC] Deletion failed for binding {}: {}"
                    _logger.exception(log.format(binding.id, message))
                    binding.message = message
                    exception |= binding
        self._remove_parents(client, done)
        return self._process_delete_done_exception(done, warning, exception)

    def _get_parents_to_remove(self, bindings):
        """After we removed some bindings, if there are no more variants that have
           a binding on this backend, then the parent is co-orphaned;
           these should thus be removed.
           We directly return the parent identifiers: [str]
        """
        parents = []
        p_with_parents = bindings.mapped("product_id").filtered("channelengine_parent")
        for template in p_with_parents.mapped("product_tmpl_id"):
            tmplt_bdgs = template.product_variant_ids.mapped("binding_ids")
            bkd_filter = lambda b: b.backend_id == self.work.backend  # noqa (E731)
            if not any(b for b in tmplt_bdgs if bkd_filter(b) and b not in bindings):
                parents.append(template.product_variant_ids[0].channelengine_parent)
        return parents

    def _remove_parents(self, client, bindings):
        parents = self._get_parents_to_remove(bindings)
        for parent in parents:
            try:
                client.product_delete(merchant_product_no=parent)
            except ApiException as e:
                _logger.exception("[CEC] Removing parent {}: {}".format(parent, e))

    def _process_delete_done_exception(self, done, warning, exception):
        done.with_context(synchronized=True).unlink()
        exception.mark_exception()
        return exception.browse(), warning, exception
