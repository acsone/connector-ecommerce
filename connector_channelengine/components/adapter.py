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

    def export(self, bindings):
        done, warning, exception = (
            bindings.browse(),
            bindings.browse(),
            bindings.browse(),
        )
        if len(bindings):  # TODO!!:batch by 10000
            client = self._get_product_client()
            data = bindings.mapped("data")
            try:
                response = client.product_create(merchant_product_request=data)
            except ApiException as e:
                _logger.exception("[CEC] {}".format(e))
                exception = bindings
            except Exception as e:  # TODO: refine handling
                message = "[CEC] {}".format(e)
                _logger.exception(message)
                raise RetryableJobError(message)
            else:
                done, warning, exception = self.process_response_messages(
                    bindings, response
                )
        return self._process_export_done_exception(done, warning, exception)

    def _process_export_done_exception(self, done, warning, exception):
        done.write({"state": "done", "exception": "ok"})
        warning.write({"state": "done", "exception": "warning"})
        exception.write({"exception": "exception"})
        return done, warning, exception

    def process_response_messages(self, bindings, response):
        done, warning, exception = (
            bindings.browse(),
            bindings.browse(),
            bindings.browse(),
        )
        # warning: 'accepted_count' may not valid if there are products without
        # MerchantProductNo (these are automatically rejected).
        if not response.success:
            return done, warning, bindings
        for message in response.content.product_messages:
            binding = bindings.filtered(
                lambda b, name=message.name: b.data["Name"] == name
            )
            if message.errors:
                exception |= binding
            elif message.warnings:
                warning |= binding
            if message.warnings or message.errors:
                timestamp = ["Date: {}".format(datetime.now())]
                all_messages = timestamp + message.warnings + message.errors
                binding.write({"message": "\n\n".join(all_messages)})
        if not len(exception) == response.content.rejected_count:
            _logger.warning(
                "[CEC] Number of exceptions improperly processed: {}".format(response)
            )
        return bindings - exception, warning, exception

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
                    log = "[CEC] Deletion failed for binding {}: {}".format(
                        binding.id, message
                    )
                    _logger.exception(log)
                    binding.message = message
                    exception |= binding
        return self._process_delete_done_exception(done, warning, exception)

    def _process_delete_done_exception(self, done, warning, exception):
        done.with_context(synchronized=True).unlink()
        exception.write({"exception": "exception"})
        return exception.browse(), warning, exception
