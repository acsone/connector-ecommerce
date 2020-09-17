# Copyright 2020 ACSONE SA/NV (<http://acsone.eu>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).


def pre_init_hook(cr):
    """The channel engine binding model depends on the method get_export_fields;
       this method returns the list of fields on its export field;
       that is to say on a record, not on a model (this is akin to a dependant type).
       Because of that the table should already exist during module install.
    """
    query = (
        'CREATE TABLE IF NOT EXISTS "channelengine_backend"'
        " (id SERIAL NOT NULL, PRIMARY KEY(id))"
    )
    cr.execute(query)
