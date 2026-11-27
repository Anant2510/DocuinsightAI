"""Adapters: an installation's own code between DocuInsights and a system of record, where settings alone are not enough.

The contract is one function (see `docuinsights.systems`):

    def lookup(system: dict, key: str, settings: dict[str, str]) -> dict:
        return {"status": "found" | "not_found" | "unavailable", "record": {"<field>": value, ...}, "reason": "..."}

`system` is the use case's declaration (its id, its name, and `fields`: the values a record carries). `key` is what to look
the record up by, as it was read from the case. `settings` holds every DOCUINSIGHTS_SYSTEM_<ID>_* value by its lower-case
name, so an adapter needs no configuration of its own. Three rules keep every adapter honest:

    * "not_found" means the system answered and holds no such record. Anything else that is not a record is "unavailable".
    * the record is flat: one value to a field, named as the use case names it.
    * nothing is cached here: the answer is the record as it stands now.

Name it in the environment (DOCUINSIGHTS_SYSTEM_<ID>_ADAPTER=package.module:function) and it is used for that system.
`newgen_rest` in this package is a reference to copy; an adapter of your own can live in any importable module.
"""
