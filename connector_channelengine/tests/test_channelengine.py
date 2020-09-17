# Copyright 2020 ACSONE SA/NV
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.addons.component.tests.common import SavepointComponentCase


class TestChannelEngine(SavepointComponentCase):
    def setUp(self):
        super(TestChannelEngine, self).setUp()

        export_id = "connector_channelengine.ir_exp_channelengine_product"
        self.backend = self.env["channelengine.backend"].create(
            {
                "name": "Test Backend",
                "export_id": self.env.ref(export_id).id,
                "domain": "[['name', '=', 'product']]",
            }
        )

        self.description = "English description"
        self.not_product = self.env["product.product"].create({"name": "notproduct"})
        self.product = self.env["product.product"].create(
            {"name": "product", "description": self.description}
        )
        product_domain = [("product_variant_ids", "in", self.product.ids)]
        self.product_template = self.env["product.template"].search(product_domain)

        self.backend.cron_check_domain()
        self.backend_filter = lambda b: b.backend_id == self.backend  # noqa
        self.binding = self.product.binding_ids.filtered(self.backend_filter)

        Langs = self.env["res.lang"].with_context(active_test=False)
        self.lang = Langs.search([("code", "=", "fr_FR")])
        self.lang.active = True
        self.env["ir.translation"].load_module_terms(["base"], [self.lang.code])

    def test_flow(self):
        """Todo...
        """
        product = self.product.copy()
        not_product = self.not_product.copy()

        message_check_new_products = "A new product should be checked for export"
        self.assertTrue(product.check_backends, message_check_new_products)
        self.assertTrue(not_product.check_backends, message_check_new_products)

        message_check_done = (
            "After the domain check, the field should have been updated."
        )
        self.backend.cron_check_domain()
        self.assertFalse(product.check_backends, message_check_done)
        self.assertFalse(not_product.check_backends, message_check_done)

        not_binding = not_product.binding_ids.filtered(self.backend_filter)
        self.assertFalse(
            not_binding,
            "This product is not in the domain so it should not have a binding.",
        )
        binding = product.binding_ids.filtered(self.backend_filter)
        self.assertTrue(
            binding, "This product is in the domain so it should have a binding."
        )
        self.assertEqual(binding.state, "todo", "It should be set to be exported.")

    def test_brand(self):
        """The brand name should be in the json iff it is set on the product.
        """
        self.assertFalse("Brand" in self.binding.data, "This product is unbranded.")
        brand = self.env["product.brand"].create({"name": "CYREN"})
        self.product.product_brand_id = brand  # triggers the recompute
        message_brand = "The brand should have been updated."
        self.assertEqual(self.binding.data["Brand"], brand.name, message_brand)

    def test_translated_field(self):
        """There is a translated field in the default export,
           that uses the translation resolver (itself putting as key fieldname_langcode)
           We check the translation is in the json, and that we get the correct value
           after putting a translated value for that field.
        """

        def get_fr_description(binding):
            for subdict in binding.data["extraData"]:
                if subdict["key"] == "description_fr_FR":
                    return subdict["value"]
            raise Exception("No fr_FR description found in the export data.")

        message_untranslated = "No translation by default."
        value_description = get_fr_description(self.binding)
        self.assertEqual(value_description, self.description, message_untranslated)
        description_francaise = "Description française, s'il vous plaît."
        self.env["ir.translation"].create(
            {
                "type": "model",
                "name": "product.template,description",
                "module": "connector_channelengine",
                "lang": self.lang.code,
                "res_id": self.product_template.id,
                "source": self.description,
                "value": description_francaise,
                "state": "translated",
            }
        )
        message_translation = "The translation should have been updated."
        value_description_fr = get_fr_description(self.binding)
        self.assertEqual(
            value_description_fr, description_francaise, message_translation
        )

    def test_export_fields(self):
        """When we modify the export of a backend, a computed field on the backend
           should update the depends on the binding data.
           Moreover, it should put existing bindings in check_backends,
           i.e. recompute their data.
        """
        new_field = "weight"
        new_value = 1
        new_dependency = "product_id.{}".format(new_field)
        depends = self.binding.get_export_fields()
        message_start = "The test would not have any interest..."
        self.assertFalse(new_dependency in depends, message_start)

        message_no_check = "The binding is already up to date."
        self.assertFalse(self.binding.check_backends, message_no_check)
        self.product[new_field] = new_value
        message_no_update = (
            "Since the field is not in the export fields, "
            "modifying it does not affect the binding."
        )
        self.assertFalse(self.binding.check_backends, message_no_update)

        resolver = self.env.ref("connector_channelengine.ir_exports_resolver_dict")
        self.env["ir.exports.line"].create(
            {
                "name": new_field,
                "alias": "{}:extraData*".format(new_field),
                "export_id": self.backend.export_id.id,
                "resolver_id": resolver.id,
            }
        )
        new_depends = self.binding.get_export_fields()
        message_new_dependency = "The new dependency should have been added"
        self.assertTrue(new_dependency in new_depends, message_new_dependency)
        message_new_check = "The new dependency should have put bindings to recompute."
        self.assertTrue(self.binding.check_backends, message_new_check)

        self.backend.cron_check_data()  # update binding data
        extra_data = self.binding.data["extraData"]
        weight_dict = [d for d in extra_data if d["key"] == new_field]
        self.assertEqual(len(weight_dict), 1, "There should be exactly one entry.")
        message_json_value = "The new value should have been obtained."
        self.assertEqual(weight_dict[0]["value"], new_value, message_json_value)

    def test_active(self):
        """The active field is implicitly always added to the backend domain.
           Thus archiving a product should ultimately set the binding to be removed.
        """
        self.assertFalse(self.product.check_backends, "This product was checked.")
        message_ready = "Binding is ready to be synchronized."
        self.assertEqual(self.binding.state, "todo", message_ready)

        self.product.active = False
        self.assertTrue(self.product.check_backends, "This product should be checked.")

        self.backend.all_check_domain(self.product)
        self.assertFalse(self.product.check_backends, "The product was processed.")
        message_to_remove = (
            "Since the product is archived, it is implicitly out of the domain, "
            "so we should remove that binding."
        )
        self.assertEqual(self.binding.state, "toremove", message_to_remove)
