This module provides a connector between ChannelEngine and Odoo.

A ChannelEngine backend corresponds to an account, which is given by a host
(the root url of the account, typically `https://yourcompany.channelengine.net/api`)
and an api_key, obtained from that account.
The latter needs to be set in an `.env` file.

ChannelEngine lets the user uploads arbitrary fields to ChannelEngine,
and configure in their web interface how these fields should be used.
There is a number of standard fields (stock, price, description, ...) as well as
any other field through extraData.
These extra fields must be given with their type information in a subdictionary.

To accommodate with these requirements without requiring custom fields or code,
a backend has an "export" field, which allows to configure each field independently.
The module comes with a default export configuration, which can entirely be customised.
It relies on "resolvers", objects to perform the needed transformations on each field.
For instance the extraData dictionary transformation come with corresponding resolvers.
For instance, `standard_price` is used for price, but any one of the hundreds of prices
that are defined on products can be used instead.
The same observation can be made for "Stock", which by default is "qty_available", but
e.g. "qty_available" (forecasted quantity) could be used instead.
The "MerchantProductNo" is essentially ChannelEngine's primary key for products.
As such, care should be taken to make sure that there is no collision on the field
which is exported as "MerchantProductNo". By default this field is `default_code`.

To be recognized as the "Color" ChannelEngine attribute, the attribute line
should be named "Color" (not color, Colour, ...), same with Size.
All other product attributes will be set in extraData as expected.

To provide translations, it is possible to set export lines with a given lang
(e.g. fr_FR), choose the corresponding field, e.g. description, and put it in extraData.
A translation resolver is provided which will automatically postfix the field name
with the export lang. An example is provided in the default export.

ChannelEngine can export products to multiple backends; to make things simple, a channel
tag is added on products so that they can be filtered easily.

To decide which products to export, a backend comes with a domain;
bindings are automatically created and removed when a product respectively
falls in or out of the domain.
This is checked every time a product is created or modified.
However if the domain depends on properties that are not directly on the product
(e.g. depends on an attribute of the product category) then this check will not
be automatically performed (and there is no way to make this possible).
In this case it is still possible to force to check existing products,
or even to create an automated action to handle such modifications, but this is
the responsibility and care of the one designing the domain.

Usage
-----

The main thing to configure as a user are the 4 ChannelEngine
scheduled actions, for the checks on data, domain, update, and remove.
Two things can be modified: each method accepts a limit argument which defaults
to zero; if set, will process only by batches of at most that many records.
The most tricky one is the remove cron, as it requires one API call per record;
thus it is the most likely to cause rate limiting issues.
Because of that, it is unadvised to set up products in a way that would frequently
delete large volumes or products, since these calls could

Monitoring
----------

The main view of the ChannelEngine app is on the bindings.
A binding symbolises the export of the product to the backend.
A binding as a state (new, todo, done, toremove), an exception state, a message, and a check.
The check means that the product data may have changed.
Thus we need to recompute its data before being able to export it.
The bindings that are not in exception state "OK" should regularly be checked.
An exception state "warning" is non-blocking, meaning the export could be performed,
whereas "exception" means that the export failed entirely.
In both cases, the message should provide an explanation on the root cause.
When a binding is in state "to remove", at the next deleter run the binding will be deleted.

On product there is a similar check; when a product is updated,
it should be checked whether a binding should be created or removed.
Forcing these recomputes can be done from the backend view.

Field list
----------

:MerchantProductNo:
    The product ID on ChannelEngine (SKU). Should be unique.
    Defaults to `default_code`.
:Name:
    The product name. Defaults to `display_name`.
:Description:
    The product description. Allows basic HTML. Defaults to `description`.
:Price:
    The price at which the product should be sold. Defaults to `price`.
:Stock:
    The product stock. Defaults to `qty_available`.
:Brand:
    The product brand. Defaults to `product_brand_id.name`.
:ImageUrl/ExtraImageUrl1/.../ExtraImageUrl9:
    Publicly accessible images for the product. Defaults to `variant_image_ids/image_url`.
:CategoryTrail:
    Essentially the product `categ_id.complete_name`. Defaults to `category_trail`.
:Size:
    The product size. Exported if the product has an attribute named `Size`, i.e. `attribute_value_ids/attribute_id/name`.
:Color:
    The product color. Exported if the product has an attribute named `Color`, i.e. `attribute_value_ids/attribute_id/name`.
:ExtraData:
    A list of ExtraData dictionaries. Each custom attribute, translations, go there.
    These can be of type NUMBER, TEXT, URL, or IMAGEURL.
    Resolvers are provided for each type.

:Url:
    A publicly accessible URL for the product. Not exported by default.
:Ean:
    The product EAN. Defaults to `barcode`.
:ManufacturerProductNumber:
    The product manufacturer catalogue identifier. Not exported by default.

:MSRP:
    The product MSRP. Not exported by default.
:PurchasePrice:
    The product purchase price. Defaults to `standard_price`.
:ShippingCost:
    The shipping cost of the product. Not exported by default.
:ShippingTime:
    A description for the expected product shipping delay.
    Not exported by default.
:VatRateType:
    One of the following four choices:
        "STANDARD", "REDUCED", "SUPER_REDUCED", "EXEMPT"

    Not exported by default.


Developer Section
-----------------

The main difficulty in this module comes from the fact that bindings
(which symbolise the export to a ChannelEngine backend) should depend on a list
of fields which is given by the backend's export.
Therefore the dependency is given by a record, and not simply by the model.
The two main problems are that at module install the corresponding table is expected
to exist already (easily solved by a pre_init hook) and the second one is to ensure
that any modification on the export changes the depends.
This second point is managed by having a stored computed field depending on the export,
which forces the setup of the binding model when it's recomputed.
It is not expected that such a modification should happen often; business-wise,
changing the export means a change in business process.
