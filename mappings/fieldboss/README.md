# FieldBOSS starter config

This config set is currently scoped to these workbook tabs:

- `Accounts`
- `Building Locations`
- `Contacts`
- `Devices`

Validated cross-sheet matches currently inferred from the orange-highlighted reference columns include:

- `Contacts`.`Company Name (Account)` -> `Accounts`.`Account Name*`
- `Building Locations`.`Customer (Account - for Invoicing)` -> `Accounts`.`Account Name*`
- `Building Locations`.`Building Owner (Account - Optional)` -> `Accounts`.`Account Name*`
- `Building Locations` contact reference columns -> `Contacts`.`Full Name (Auto)`
- `Devices`.`Building Location` -> `Building Locations`.`Name*`
- `Devices`.`Account` -> `Accounts`.`Account Name*`