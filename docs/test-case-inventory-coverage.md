# Test Case Inventory Coverage

This document maps the supplied issue inventory to the current starter implementation.

## Covered now

### 1. Identity & duplication issues
- Exact duplicates for:
  - `Accounts.Account Name*`
  - `Accounts.Legacy Customer #`
  - `Building Locations.Legacy Building #`
  - `Building Locations.Name* + Customer (Account - for Invoicing)`
  - `Contacts.Email`
  - `Contacts.First Name + Last Name* + Company Name (Account)`
  - `Contacts.Full Name (Auto)` (logged)
  - `Devices.Device ID`
  - `Devices.Device Number`
- Near / fuzzy duplicate logging now normalizes:
  - case differences
  - leading/trailing whitespace
  - punctuation
  - common aliases like `Building` / `Bldg`

### 2. Referential integrity failures
- Orphaned references are flagged for:
  - Buildings -> Accounts
  - Contacts -> Accounts
  - Devices -> Buildings
  - Devices -> Accounts
  - Account / Building contact references -> `Contacts.Full Name (Auto)`
- Mixed-case or normalized near-match references now get clearer logging when a similar value exists.
- Device-to-building/account consistency checks added:
  - `Devices.Account` must match the account tied to the referenced building
  - `Devices.Legacy Building ID` must agree with `Devices.Building Location`

### 3. Required field violations
- Required core names are already enforced:
  - `Account Name*`
  - `Building Name*`
  - `Device Name*`
  - `Contacts.Last Name*`
- Partial-address rules now flag rows where only some address fields are populated.

### 4. Malformed / invalid field data
- Numeric constraints added for:
  - `Building Locations.# Elevators` (must be integer and >= 1)
  - `Tax Rate` (must be numeric and >= 0 if present)
- Format validation added for:
  - email fields
  - phone fields
  - US / Canadian postal codes
- Placeholder enum values like `???` are now flagged for:
  - `Account Type`
  - `Contact Type`
  - `Device Type`

### 5. Locale / normalization issues
- Country normalization now maps common inputs like `USA`, `US`, `Canada`, `CA` into canonical values.
- Province/state code validation now checks the code against the selected country where that country is present on the row.
- Null-like strings such as `None`, `NULL`, `N/A`, and blank strings are standardized as empty values.

### 6. Semantic / business logic conflicts
- Account self-parenting is flagged.
- Circular parent-account chains are flagged.
- Buildings with more assigned devices than `# Elevators` are flagged.

### 7. Temporal / ordering hazards
- The pipeline stages all rows before cross-sheet validation, so child rows appearing before parents are handled.
- Mixed valid / invalid references under the same parent are evaluated after the full workbook is indexed.

## Partially covered / future tightening
- True city-to-province validation such as `Toronto + MA` or `Boston + ON` is **not fully implemented** without a trusted geography reference set.
- Full business-rule validation for every orange reference column can be extended once the populated sheets are available.
- Ambiguous duplicate resolution is still **log-and-review** rather than auto-merge.

## Output files for validation review
- `output/Accounts_errors.csv`
- `output/Building Locations_errors.csv`
- `output/Contacts_errors.csv`
- `output/Devices_errors.csv`
- `logs/duplicate_log.csv`
- `logs/run_log.csv`
